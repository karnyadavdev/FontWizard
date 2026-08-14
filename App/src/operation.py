import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont

from font_cache import refresh_windows_font_cache
from font_generation import build_font
from fonts import validate_selection
from operation_files import (
    backup_canonical_fonts,
    cleanup_orphaned_pending_ops,
    purge_system_font_cache,
    schedule_canonical_replacement,
    schedule_canonical_restore,
)
from settings import FONTS_DIR, default_registry_targets
from app_state import hash_file, iso_now


@dataclass
class OperationResult:
    success: bool
    message: str
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class FontWorkflow:
    def __init__(
        self,
        paths,
        registry,
        state_store,
        preflight,
        identity_fonts_root=None,
        active_fonts_root=None,
    ):
        self.paths = paths
        self.registry = registry
        self.state_store = state_store
        self.preflight = preflight
        self.identity_fonts_root = Path(identity_fonts_root or FONTS_DIR)
        self.active_fonts_root = Path(active_fonts_root or FONTS_DIR)

    def _system_weights(self):
        from settings import get_system_weights
        return get_system_weights(self.identity_fonts_root)

    def _system_font_files(self):
        return list(dict.fromkeys(self._system_weights().values()))

    def validate(self, selection, source_labels=None):
        return validate_selection(selection, source_labels, weights=self._system_weights())

    def apply(self, selection, source_labels=None, progress=None):
        report = self.preflight.collect()
        if not report.is_supported:
            return OperationResult(False, "Font Wizard supports Windows 10 (build 10240+) and Windows 11.", report.issues, report.warnings)

        if not report.is_admin:
            return OperationResult(False, "Run Font Wizard as Administrator before applying fonts.", report.issues, report.warnings)

        if report.install_state == "pending_reboot_recovery":
            return OperationResult(
                False,
                "Restart Windows before applying another font.",
                ["A previous recovery still has file updates waiting for restart."],
                report.warnings,
            )

        summary = self.validate(selection, source_labels)
        if not summary.ok:
            return OperationResult(False, summary.errors[0] if summary.errors else "The selected font cannot be used.", summary.errors, summary.warnings)

        stage_dir = self.paths.make_temp_dir("fontwizard-build-")
        system_files = self._system_font_files()

        try:
            self._emit(progress, 5, "Backing up original Windows system fonts...")
            backup_warnings, backed_count = backup_canonical_fonts(self, system_files)

            self._emit(progress, 15, "Cleaning up old pending operations...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)

            self._emit(progress, 30, "Compiling custom TrueType font weights...")
            artifacts = build_artifacts(self, summary.entries, stage_dir)

            self._emit(progress, 75, "Scheduling physical in-place replacement on boot...")
            manifest, schedule_warnings = schedule_canonical_replacement(self, artifacts)

            self._emit(progress, 88, "Purging system font caches...")
            cache_warnings = purge_system_font_cache()
            refresh_windows_font_cache()

            # Ensure Segoe WPC substitute is set in registry
            try:
                self.registry.ensure_font_substitutes()
            except Exception:
                pass

            self._emit(progress, 95, "Saving installation state...")
            state = self.state_store.load_or_empty()
            state["install"] = {
                "status": "pending_reboot_apply",
                "fonts": manifest,
                "backed_up_count": backed_count,
                "applied_at": iso_now(),
                "restored_at": None,
            }
            state["last_action"] = {
                "kind": "apply",
                "status": "success",
                "timestamp": iso_now(),
                "details": "Scheduled physical in-place replacement on boot.",
            }
            self.state_store.save(state)

            self._emit(progress, 100, "Font setup complete!")
            all_warnings = [
                *summary.warnings,
                *backup_warnings,
                *pending_cleanup_warnings,
                *schedule_warnings,
                *cache_warnings,
            ]
            return OperationResult(
                True,
                "Physical replacement scheduled. Restart Windows now to finish applying the font.",
                warnings=all_warnings,
            )
        except Exception as exc:
            state = self.state_store.load_or_empty()
            state["last_action"] = {
                "kind": "apply",
                "status": "failed",
                "timestamp": iso_now(),
                "details": str(exc),
            }
            self.state_store.save(state)
            return OperationResult(False, f"Failed to apply font changes: {exc}", [str(exc)], summary.warnings)
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)

    def restore(self, progress=None):
        report = self.preflight.collect()
        if not report.is_admin:
            return OperationResult(False, "Run Font Wizard as Administrator before restoring fonts.", report.issues, report.warnings)

        system_files = self._system_font_files()

        try:
            self._emit(progress, 10, "Cleaning up stale pending files...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)

            self._emit(progress, 35, "Scheduling restore of original fonts on boot...")
            scheduled_count, restore_warnings = schedule_canonical_restore(self, system_files)
            if scheduled_count == 0:
                return OperationResult(
                    False,
                    "Failed to schedule font restore: No authentic backup font files were found.",
                    restore_warnings,
                )

            self._emit(progress, 75, "Purging system font caches...")
            cache_warnings = purge_system_font_cache()
            refresh_windows_font_cache()

            self._emit(progress, 92, "Saving restore state...")
            state = self.state_store.load_or_empty()
            state["install"] = {
                "status": "pending_reboot_recovery",
                "fonts": {},
                "applied_at": state.get("install", {}).get("applied_at"),
                "restored_at": iso_now(),
            }
            state["last_action"] = {
                "kind": "restore",
                "status": "success",
                "timestamp": iso_now(),
                "details": f"Scheduled restore of {scheduled_count} original Microsoft fonts on boot.",
            }
            self.state_store.save(state)

            self._emit(progress, 100, "Font restore scheduled!")
            all_warnings = [
                *pending_cleanup_warnings,
                *restore_warnings,
                *cache_warnings,
            ]
            return OperationResult(
                True,
                f"Original Windows fonts ({scheduled_count}/{len(system_files)}) scheduled for restore. Restart Windows now to finish.",
                warnings=all_warnings,
            )
        except Exception as exc:
            return OperationResult(False, f"Font restore failed: {exc}", [str(exc)])

    def _emit(self, callback, value, message):
        if callback:
            callback(value, message)


def _verify_build_output(output_path: Path, segoe_path: Path):
    built_font = None
    donor_font = None
    try:
        try:
            built_font = TTFont(output_path)
        except Exception as exc:
            raise RuntimeError(f"Built font could not be reopened: {output_path.name}") from exc

        try:
            donor_font = TTFont(segoe_path)
        except Exception as exc:
            raise RuntimeError(f"Could not inspect donor font: {segoe_path.name}") from exc

        expected = {
            "family_name": donor_font["name"].getBestFamilyName(),
            "full_name": donor_font["name"].getBestFullName(),
            "subfamily_name": donor_font["name"].getBestSubFamilyName(),
            "mac_style": donor_font["head"].macStyle,
            "os2_version": donor_font["OS/2"].version,
            "weight_class": donor_font["OS/2"].usWeightClass,
            "width_class": donor_font["OS/2"].usWidthClass,
            "fs_selection": donor_font["OS/2"].fsSelection,
            "italic_angle": donor_font["post"].italicAngle,
        }
        actual = {
            "family_name": built_font["name"].getBestFamilyName(),
            "full_name": built_font["name"].getBestFullName(),
            "subfamily_name": built_font["name"].getBestSubFamilyName(),
            "mac_style": built_font["head"].macStyle,
            "os2_version": built_font["OS/2"].version,
            "weight_class": built_font["OS/2"].usWeightClass,
            "width_class": built_font["OS/2"].usWidthClass,
            "fs_selection": built_font["OS/2"].fsSelection,
            "italic_angle": built_font["post"].italicAngle,
        }

        for key, expected_value in expected.items():
            if actual[key] != expected_value:
                raise RuntimeError(
                    f"Built font identity check failed for {output_path.name}: "
                    f"{key} was {actual[key]!r}, expected {expected_value!r}."
                )
    finally:
        if built_font is not None:
            built_font.close()
        if donor_font is not None:
            donor_font.close()


def build_artifacts(workflow, entries, stage_dir):
    artifacts = {}
    for entry in entries:
        segoe_path = workflow.identity_fonts_root / entry.system_filename
        output_path = stage_dir / entry.system_filename

        build_font(entry.source_path, segoe_path, output_path)
        _verify_build_output(output_path, segoe_path)

        artifacts[entry.weight] = {
            "weight": entry.weight,
            "registry_name": entry.registry_name,
            "system_filename": entry.system_filename,
            "generated_filename": entry.system_filename,
            "source_path": str(entry.source_path),
            "family_name": entry.family_name,
            "full_name": entry.full_name,
            "staged_path": str(output_path),
            "hash": hash_file(output_path),
        }
    return artifacts
