import shutil
from dataclasses import dataclass, field
from pathlib import Path

from fontTools.ttLib import TTFont

from font_cache import refresh_windows_font_cache
from font_generation import build_font, build_variable_font
from fonts import validate_selection
from journal import JOURNAL_FILENAME, OperationJournal
from operation_files import (
    backup_and_override_system_fonts,
    cleanup_font_directory_artifacts,
    cleanup_managed_fonts,
    cleanup_orphaned_pending_ops,
    install_transaction,
    restore_original_fonts,
    rollback,
    sanitize_previous_registry,
)
from settings import CONSOLAS_WEIGHTS, CONSOLAS_REGISTRY_NAMES, FONTS_DIR, WEIGHTS, default_registry_targets
from app_state import hash_file, iso_now

DEFAULT_FONT_SUBSTITUTES = {
    "MS Shell Dlg": "Microsoft Sans Serif",
    "MS Shell Dlg 2": "Tahoma",
}

_APP_SET_SUBSTITUTES = {
    "MS Shell Dlg": "Segoe UI",
    "MS Shell Dlg 2": "Segoe UI",
}


@dataclass
class OperationResult:
    success: bool
    message: str
    details: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def detect_mono_family(font_path):
    """Auto-map the 4 Consolas slots from a base mono font (legacy single-pick)."""
    fallback = {weight: font_path for weight in CONSOLAS_WEIGHTS}
    try:
        from font_detection import detect_weight_overrides

        mono_selection = detect_weight_overrides(
            font_path,
            {"regular": font_path},
        )
    except ValueError:
        return fallback
    mono_selection.setdefault("regular", font_path)
    for weight in CONSOLAS_WEIGHTS:
        if weight not in mono_selection:
            mono_selection[weight] = font_path
    return mono_selection


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
        return list(dict.fromkeys([*WEIGHTS.values(), *CONSOLAS_WEIGHTS.values()]))

    def _effective_monospace_paths(self, monospace_paths):
        if monospace_paths is None:
            monospace_paths = {}
        return monospace_paths

    def validate(self, selection, source_labels=None, monospace_paths=None):
        monospace_paths = self._effective_monospace_paths(monospace_paths)
        family = {"system_files": CONSOLAS_WEIGHTS, "registry_names": CONSOLAS_REGISTRY_NAMES}
        if monospace_paths:
            family["source"] = dict(monospace_paths)
        return validate_selection(
            selection,
            source_labels,
            extra_families=[family],
        )

    def apply(self, selection, source_labels=None, progress=None, monospace_paths=None):
        monospace_paths = self._effective_monospace_paths(monospace_paths)
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


        summary = self.validate(selection, source_labels, monospace_paths)
        if not summary.ok:
            return OperationResult(False, summary.errors[0] if summary.errors else "The selected font cannot be used.", summary.errors, summary.warnings)

        stage_dir = self.paths.make_temp_dir("fontwizard-build-")
        rollback_dir = self.paths.make_temp_dir("fontwizard-rollback-")
        artifacts = {}
        saved_state = self.state_store.load() or {}
        existing_install = saved_state.get("install", {})
        previous_registry = None
        if existing_install.get("status") in ("applied", "pending_reboot", "pending_reboot_apply"):
            saved_registry = existing_install.get("previous_registry")
            if isinstance(saved_registry, dict) and saved_registry:
                previous_registry = saved_registry
        if not previous_registry:
            previous_registry = self.registry.read_targets(list(default_registry_targets().keys()))
        previous_registry = sanitize_previous_registry(previous_registry)
        saved_substitutes = existing_install.get("previous_substitutes")
        previous_substitutes = saved_substitutes or self.registry.read_substitutes()
        protected_active_fonts = set(previous_registry.values())

        journal = OperationJournal(self.paths.data_root / JOURNAL_FILENAME)
        journal.begin(
            "apply",
            {
                "selection": {weight: (str(path) if path else None) for weight, path in selection.items()},
                "source_labels": dict(source_labels or {}),
                "monospace_paths": {weight: (str(path) if path else None) for weight, path in monospace_paths.items()},
            },
            previous_registry,
        )
        journal.add_temp_dir(stage_dir)
        journal.add_temp_dir(rollback_dir)

        try:
            self._emit(progress, 2, "Cleaning up old pending file changes...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)
            font_dir_cleanup_warnings, _ = cleanup_font_directory_artifacts(
                self,
                protected_files=protected_active_fonts,
            )
            journal.record_step("cleanup")

            self._emit(progress, 20, "Preparing managed font files...")
            artifacts = build_artifacts(self, summary.entries, stage_dir)
            journal.record_step("build")

            self._emit(progress, 70, "Installing the selected font files...")
            install_manifest = install_transaction(self, artifacts, previous_registry, rollback_dir, previous_substitutes)
            journal.record_step("install")

            self._emit(progress, 84, "Applying the font to the protected system copies...")
            system_warnings = backup_and_override_system_fonts(self, install_manifest["fonts"], progress)
            journal.record_step("override_system_fonts")

            self._emit(progress, 88, "Refreshing the Windows font cache...")
            cache_warnings = refresh_windows_font_cache()
            install_warnings = install_manifest.get("warnings", [])
            journal.record_step("cache_refresh")

            self._emit(progress, 92, "Saving the current Font Wizard state...")
            state = self.state_store.load_or_empty()
            install_manifest["options"] = {
                "monospace_paths": {weight: (str(path) if path else None) for weight, path in monospace_paths.items()},
            }
            state["install"] = install_manifest
            state["last_action"] = {
                "kind": "apply",
                "status": "success",
                "timestamp": iso_now(),
                "details": "Apply completed.",
            }
            self.state_store.save(state)
            journal.record_step("state_save")

            self._emit(progress, 100, "Font apply completed.")
            journal.clear()
            return OperationResult(
                True,
                "Fonts were updated. Restart Windows to finish the change.",
                warnings=[
                    *summary.warnings,
                    *pending_cleanup_warnings,
                    *font_dir_cleanup_warnings,
                    *install_warnings,
                    *system_warnings,
                    *cache_warnings,
                ],
            )
        except Exception as exc:
            rollback(self, previous_registry, artifacts, rollback_dir, previous_substitutes)
            journal.clear()

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
        if report.install_state == "pending_reboot_apply":
            return OperationResult(
                False,
                "Restart Windows before restoring the original fonts.",
                ["A previous font change still has file updates waiting for restart."],
                report.warnings,
            )

        defaults = default_registry_targets()
        previous_registry = self.registry.read_targets(list(defaults.keys()))
        state = self.state_store.load_or_empty()
        previous_substitutes = state.get("install", {}).get("previous_substitutes") or {}

        journal = OperationJournal(self.paths.data_root / JOURNAL_FILENAME)
        journal.begin("restore", {}, previous_registry)

        try:
            self._emit(progress, 2, "Cleaning up old pending file changes...")
            pending_cleanup_warnings, is_pending1 = cleanup_orphaned_pending_ops(self)
            font_dir_cleanup_warnings, is_pending2 = cleanup_font_directory_artifacts(self)
            journal.record_step("cleanup")

            self._emit(progress, 20, "Restoring the original system font files...")
            restored, missing_originals, restore_warnings, deferred_system_fonts = restore_original_fonts(self, progress=progress)
            kept_system_filenames = {
                system_file
                for system_file in missing_originals
                if not (self.active_fonts_root / system_file).exists()
            }
            if missing_originals:
                repointed = sorted(set(missing_originals) - kept_system_filenames)
                if repointed:
                    restore_warnings.append(
                        "Original files were not found in the Font Wizard backup folder for: "
                        + ", ".join(repointed)
                        + ". Their registry entries were repointed to the system copies still present."
                    )
                if kept_system_filenames:
                    restore_warnings.append(
                        "Original files were not found in the Font Wizard backup folder for: "
                        + ", ".join(sorted(kept_system_filenames))
                        + ". Those weights keep the custom font until the originals are restored."
                    )
            journal.record_step("restore_system_fonts")

            targets_to_write = {
                name: filename
                for name, filename in defaults.items()
                if (self.active_fonts_root / filename).exists()
            }

            self._emit(progress, 35, "Restoring the Windows font registry entries...")
            self.registry.write_targets(targets_to_write)
            substitutes_warnings = []
            final_substitutes = previous_substitutes or {}
            if previous_substitutes:
                try:
                    self.registry.write_substitutes(previous_substitutes)
                except Exception as exc:
                    substitutes_warnings.append(f"Could not restore the original MS Shell Dlg registry substitute: {exc}")
            else:
                current_substitutes = self.registry.read_substitutes()
                if any(
                    (current_substitutes.get(name) or "").strip().lower() == value.lower()
                    for name, value in _APP_SET_SUBSTITUTES.items()
                ):
                    try:
                        self.registry.write_substitutes(DEFAULT_FONT_SUBSTITUTES)
                        final_substitutes = DEFAULT_FONT_SUBSTITUTES
                        substitutes_warnings.append(
                            "The original MS Shell Dlg substitutes were not recorded by the previous version, "
                            "so they were reset to the Windows defaults (Microsoft Sans Serif / Tahoma)."
                        )
                    except Exception as exc:
                        substitutes_warnings.append(
                            f"Could not reset the MS Shell Dlg registry substitute: {exc}"
                        )
                else:
                    substitutes_warnings.append(
                        "The original MS Shell Dlg substitutes were not recorded, so they were left unchanged."
                    )
            journal.record_step("registry")

            self._emit(progress, 60, "Cleaning up Font Wizard font files...")
            cleanup_warnings, is_pending3 = cleanup_managed_fonts(
                self,
                previous_registry,
                state,
                keep_system_filenames=kept_system_filenames,
            )
            journal.record_step("cleanup_managed_fonts")

            self._emit(progress, 88, "Refreshing the Windows font cache...")
            cache_warnings = refresh_windows_font_cache()
            journal.record_step("cache_refresh")
            
            is_pending = is_pending1 or is_pending2 or is_pending3 or bool(deferred_system_fonts)

            state["install"] = {
                "status": "pending_reboot" if is_pending else "clean",
                "registry_targets": defaults,
                "fonts": {},
                "previous_registry": previous_registry,
                "previous_substitutes": final_substitutes,
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
            journal.record_step("state_save")
            journal.clear()
            self._emit(progress, 100, "Font restore completed.")

            warnings = [
                *pending_cleanup_warnings,
                *font_dir_cleanup_warnings,
                *restore_warnings,
                *substitutes_warnings,
                *cleanup_warnings,
                *cache_warnings,
            ]

            message = "The original Windows fonts have been restored."
            if deferred_system_fonts:
                message += " Some system font files are locked and will be restored after you restart Windows."
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
            if not segoe_path.exists():
                continue
            build_variable_font(entry.source_path, segoe_path, output_path)
        else:
            build_font(entry.source_path, segoe_path, output_path)
            _verify_build_output(output_path, segoe_path)

        artifacts[entry.registry_name] = {
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
