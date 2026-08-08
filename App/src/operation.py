import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont

from font_cache import refresh_windows_font_cache
from font_generation import build_font, build_variable_font
from fonts import validate_selection
from operation_files import (
    cleanup_font_directory_artifacts,
    cleanup_managed_fonts,
    cleanup_orphaned_pending_ops,
    install_transaction,
    rollback,
)
from settings import FONTS_DIR, WEIGHTS, default_registry_targets
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

    def _system_font_files(self):
        return list(dict.fromkeys(WEIGHTS.values()))

    def validate(self, selection, source_labels=None):
        return validate_selection(selection, source_labels)

    def apply(self, selection, source_labels=None, progress=None):
        report = self.preflight.collect()
        if not report.is_supported:
            return OperationResult(False, "Font Wizard only supports Windows 11.", report.issues, report.warnings)
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
        rollback_dir = self.paths.make_temp_dir("fontwizard-rollback-")
        artifacts = {}
        previous_registry = self.registry.read_targets(list(default_registry_targets().keys()))
        protected_active_fonts = set(previous_registry.values())

        try:
            self._emit(progress, 2, "Cleaning up old pending file changes...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)
            font_dir_cleanup_warnings, _ = cleanup_font_directory_artifacts(
                self,
                protected_files=protected_active_fonts,
            )

            self._emit(progress, 20, "Preparing managed font files...")
            artifacts = build_artifacts(self, summary.entries, stage_dir)

            self._emit(progress, 70, "Installing the selected font files...")
            install_manifest = install_transaction(self, artifacts, previous_registry, rollback_dir)
            
            self._emit(progress, 88, "Refreshing the Windows font cache...")
            cache_warnings = refresh_windows_font_cache()
            install_warnings = install_manifest.get("warnings", [])

            self._emit(progress, 92, "Saving the current Font Wizard state...")
            state = self.state_store.load_or_empty()
            state["install"] = install_manifest
            state["last_action"] = {
                "kind": "apply",
                "status": "success",
                "timestamp": iso_now(),
                "details": "Apply completed.",
            }
            self.state_store.save(state)

            self._emit(progress, 100, "Font apply completed.")
            return OperationResult(
                True,
                "Fonts were updated. Restart Windows to finish the change.",
                warnings=[
                    *summary.warnings,
                    *pending_cleanup_warnings,
                    *font_dir_cleanup_warnings,
                    *install_warnings,
                    *cache_warnings,
                ],
            )
        except Exception as exc:
            rollback(self, previous_registry, artifacts, rollback_dir)
            
            state = self.state_store.load_or_empty()
            state["last_action"] = {
                "kind": "apply",
                "status": "failed",
                "timestamp": iso_now(),
                "details": str(exc),
            }
            self.state_store.save(state)
            return OperationResult(False, "Something went wrong while applying. Your previous fonts were restored.", [str(exc)], summary.warnings)
        finally:
            shutil.rmtree(stage_dir, ignore_errors=True)
            shutil.rmtree(rollback_dir, ignore_errors=True)

    def restore(self, progress=None):
        report = self.preflight.collect()
        if not report.is_admin:
            return OperationResult(False, "Run Font Wizard as Administrator before restoring fonts.", report.issues, report.warnings)

        defaults = default_registry_targets()
        previous_registry = self.registry.read_targets(list(defaults.keys()))
        state = self.state_store.load_or_empty()

        try:
            self._emit(progress, 2, "Cleaning up old pending file changes...")
            pending_cleanup_warnings, is_pending1 = cleanup_orphaned_pending_ops(self)
            font_dir_cleanup_warnings, is_pending2 = cleanup_font_directory_artifacts(self)

            self._emit(progress, 30, "Restoring the Windows font registry entries...")
            self.registry.write_targets(defaults)

            self._emit(progress, 60, "Cleaning up Font Wizard font files...")
            cleanup_warnings, is_pending3 = cleanup_managed_fonts(self, previous_registry, state)

            self._emit(progress, 88, "Refreshing the Windows font cache...")
            cache_warnings = refresh_windows_font_cache()
            
            is_pending = is_pending1 or is_pending2 or is_pending3

            state["install"] = {
                "status": "pending_reboot" if is_pending else "clean",
                "registry_targets": defaults,
                "fonts": {},
                "previous_registry": previous_registry,
                "applied_at": state.get("install", {}).get("applied_at"),
                "restored_at": iso_now(),
            }
            state["last_action"] = {
                "kind": "restore",
                "status": "success",
                "timestamp": iso_now(),
                "details": "Restore completed.",
            }
            self.state_store.save(state)
            self._emit(progress, 100, "Font restore completed.")

            warnings = [
                *pending_cleanup_warnings,
                *font_dir_cleanup_warnings,
                *cleanup_warnings,
                *cache_warnings,
            ]

            message = "The original Windows fonts have been restored."
            if cleanup_warnings:
                message += " Some files are still in use and will be cleaned up after you restart Windows."
            return OperationResult(True, message, warnings=warnings)
        except Exception as exc:
            return OperationResult(False, "Font restore did not finish. Some changes may have been made.", [str(exc)])

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
        output_path = stage_dir / entry.generated_filename

        if entry.weight == "variable":
            build_variable_font(entry.source_path, segoe_path, output_path)
        else:
            build_font(entry.source_path, segoe_path, output_path)
            _verify_build_output(output_path, segoe_path)

        artifacts[entry.weight] = {
            "weight": entry.weight,
            "registry_name": entry.registry_name,
            "system_filename": entry.system_filename,
            "generated_filename": entry.generated_filename,
            "source_path": str(entry.source_path),
            "family_name": entry.family_name,
            "full_name": entry.full_name,
            "staged_path": str(output_path),
            "hash": hash_file(output_path),
        }
    return artifacts
