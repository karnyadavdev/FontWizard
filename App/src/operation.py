import os
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
    purge_fontwizard_pending_renames,
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

    def _system_font_files(self, *, include_regional: bool = True):
        from settings import get_existing_mono_companions, get_existing_regional_targets, get_existing_ui_companions
        files = list(dict.fromkeys(self._system_weights().values()))
        target_dir = self.identity_fonts_root if self.identity_fonts_root.exists() else self.active_fonts_root
        for companion_file in get_existing_mono_companions(target_dir):
            if companion_file not in files:
                files.append(companion_file)
        for companion_file in get_existing_ui_companions(target_dir):
            if companion_file not in files:
                files.append(companion_file)
        if include_regional:
            for regional_file in get_existing_regional_targets(target_dir):
                if regional_file not in files:
                    files.append(regional_file)
        return files

    def validate(self, selection, source_labels=None):
        return validate_selection(selection, source_labels, weights=self._system_weights())

    def apply(self, selection, source_labels=None, progress=None, *, include_regional: bool = True):
        report = self.preflight.collect(include_regional=include_regional)
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

        if report.issues:
            return OperationResult(False, report.issues[0], report.issues, report.warnings)

        summary = self.validate(selection, source_labels)
        if not summary.ok:
            return OperationResult(False, summary.errors[0] if summary.errors else "The selected font cannot be used.", summary.errors, summary.warnings)

        stage_dir = self.paths.make_temp_dir("fontwizard-build-")
        system_files = self._system_font_files(include_regional=include_regional)

        try:
            self._emit(progress, 5, "Backing up original Windows system fonts...")
            backup_warnings, backed_count = backup_canonical_fonts(self, system_files)

            if backed_count < len(system_files):
                backup_warnings.append(
                    f"Note: {backed_count} of {len(system_files)} original fonts were backed up."
                )

            # Scrub old FontWizard pending operations to prevent collisions
            purge_warnings = purge_fontwizard_pending_renames()

            # Gap A: If Asian Stacks is OFF, revert any previously modified/pending regional fonts
            revert_warnings = []
            failed_regional_reverts = []
            if not include_regional:
                state = self.state_store.load_or_empty()
                installed_fonts = state.get("install", {}).get("fonts", {})
                from settings import get_existing_regional_targets
                target_dir = self.identity_fonts_root if self.identity_fonts_root.exists() else self.active_fonts_root
                reg_targets = list(get_existing_regional_targets(target_dir).keys())
                has_regional_applied = any(k.startswith("regional_") for k in installed_fonts)
                has_regional_staged = any(
                    (self.active_fonts_root / f"staged_replace_{reg_name}").exists() or
                    (self.active_fonts_root / f"staged_restore_{reg_name}").exists()
                    for reg_name in reg_targets
                )
                if has_regional_applied or has_regional_staged:
                    stale_regional_targets = []
                    for reg_name in reg_targets:
                        reg_key = f"regional_{reg_name.lower().replace('.', '_')}"
                        staged_old = self.active_fonts_root / f"staged_replace_{reg_name}"
                        staged_res = self.active_fonts_root / f"staged_restore_{reg_name}"
                        if staged_old.exists() or staged_res.exists() or (reg_key in installed_fonts):
                            stale_regional_targets.append(reg_name)
                    if stale_regional_targets:
                        self._emit(progress, 15, "Reverting previous Asian font modifications...")
                        _, _, _, revert_warnings = schedule_canonical_restore(
                            self, stale_regional_targets, failed_names=failed_regional_reverts
                        )
                        if failed_regional_reverts:
                            return OperationResult(
                                False,
                                "Cannot safely switch off Asian font stacks: previous regional fonts could not be restored.\n\n"
                                "Please check available disk space or run 'sfc /scannow' to recover original regional fonts.",
                                backup_warnings + revert_warnings,
                            )

            self._emit(progress, 20, "Cleaning up old pending operations...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)

            # Pre-compilation safety gate: Verify backups exist for mandatory core system fonts before heavy compilation
            from operation_files import find_original_font_backup
            from settings import STATIC_WEIGHTS, VARIABLE_WEIGHTS
            mandatory_files = set(STATIC_WEIGHTS.values())
            if (self.identity_fonts_root / "SegUIVar.ttf").exists():
                mandatory_files.update(VARIABLE_WEIGHTS.values())

            core_candidates = [e.system_filename for e in summary.entries if e.system_filename in mandatory_files]
            missing_backups = [f for f in core_candidates if find_original_font_backup(self, f) is None]
            if missing_backups:
                return OperationResult(
                    False,
                    f"Cannot safely apply fonts: missing verified original backup for core system font(s): {', '.join(missing_backups)}.\n\n"
                    "Run 'sfc /scannow' in an Administrator terminal to restore your original Windows system fonts, then try applying again.",
                    backup_warnings,
                )

            self._emit(progress, 30, "Compiling custom TrueType font weights...")
            build_warnings = []
            artifacts = build_artifacts(self, summary.entries, stage_dir, build_warnings, include_regional=include_regional, progress=progress)

            # Safety gate: Ensure all fonts being replaced have verified authentic backups before touching anything
            from operation_files import find_original_font_backup
            target_files = list(dict.fromkeys(item["system_filename"] for item in artifacts.values()))
            missing_backups = [f for f in target_files if find_original_font_backup(self, f) is None]
            if missing_backups:
                cascadia_missing = [f for f in missing_backups if "cascadia" in f.lower()]
                system_missing = [f for f in missing_backups if "cascadia" not in f.lower()]
                remedies = []
                if system_missing:
                    remedies.append("Run 'sfc /scannow' in an Administrator terminal to restore your original Windows system fonts")
                if cascadia_missing:
                    remedies.append("reinstall/repair Windows Terminal or Visual Studio to recover Cascadia fonts")
                remedy_text = " and ".join(remedies)
                return OperationResult(
                    False,
                    f"Cannot safely apply fonts: missing verified original backup for font(s): {', '.join(missing_backups[:5])}{'...' if len(missing_backups) > 5 else ''}.\n\n"
                    f"{remedy_text}, then try applying again.",
                    backup_warnings + build_warnings,
                )

            self._emit(progress, 75, "Scheduling physical in-place replacement on boot...")
            manifest, schedule_warnings = schedule_canonical_replacement(self, artifacts)
            if artifacts and not manifest:
                return OperationResult(
                    False,
                    "Windows could not schedule the font replacement on boot.\n\n"
                    "Please ensure Font Wizard is running as Administrator and no security software is blocking boot file replacement.",
                    backup_warnings + build_warnings + schedule_warnings,
                )

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
            if failed_regional_reverts:
                old_fonts = state.get("install", {}).get("fonts", {})
                for reg_name in failed_regional_reverts:
                    reg_key = f"regional_{reg_name.lower().replace('.', '_')}"
                    if reg_key in old_fonts:
                        failed_entry = dict(old_fonts[reg_key])
                        failed_entry["status"] = "revert_failed"
                        manifest[reg_key] = failed_entry
                    else:
                        manifest[reg_key] = {
                            "system_filename": reg_name,
                            "status": "revert_failed",
                        }

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
                *purge_warnings,
                *revert_warnings,
                *pending_cleanup_warnings,
                *build_warnings,
                *schedule_warnings,
                *cache_warnings,
            ]
            return OperationResult(
                True,
                "Font changes scheduled. Restart Windows now to finish applying your font.",
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
        report = self.preflight.collect(include_regional=True, is_restore=True)
        if not report.is_admin:
            return OperationResult(False, "Run Font Wizard as Administrator before restoring fonts.", report.issues, report.warnings)

        if report.issues:
            return OperationResult(False, report.issues[0], report.issues, report.warnings)

        purge_warnings = purge_fontwizard_pending_renames()
        system_files = self._system_font_files(include_regional=True)

        # Include any legacy fonts tracked in state from previous installs (e.g. Cascadia Code/Mono)
        state_data = self.state_store.load_or_empty()
        installed_fonts = state_data.get("install", {}).get("fonts", {})
        if isinstance(installed_fonts, dict):
            for font_info in installed_fonts.values():
                if isinstance(font_info, dict):
                    fn = font_info.get("system_filename")
                    if fn and fn not in system_files:
                        system_files.append(fn)

        try:
            self._emit(progress, 10, "Cleaning up stale pending files...")
            pending_cleanup_warnings, _ = cleanup_orphaned_pending_ops(self)

            self._emit(progress, 35, "Scheduling restore of original fonts on boot...")
            failed_targets = []
            scheduled_count, skipped_count, failed_count, restore_warnings = schedule_canonical_restore(
                self, system_files, failed_names=failed_targets
            )

            if failed_count > 0 and scheduled_count == 0:
                if any("authentic backup file missing" in w.lower() for w in restore_warnings) and not any("could not stage" in w.lower() for w in restore_warnings):
                    return OperationResult(
                        False,
                        "No authentic backup font files were found. You can restore original Windows fonts by running 'sfc /scannow' or 'DISM /Online /Cleanup-Image /RestoreHealth' in an Administrator terminal.",
                        restore_warnings,
                    )
                return OperationResult(
                    False,
                    "Failed to restore original fonts due to insufficient disk space or missing backup files. No changes were applied.",
                    restore_warnings,
                )

            if scheduled_count == 0:
                message = "Original Windows fonts are already active. System is clean."
            elif failed_count > 0:
                cascadia_failed = [f for f in failed_targets if "cascadia" in f.lower()]
                system_failed = [f for f in failed_targets if "cascadia" not in f.lower()]
                remedies = []
                if system_failed:
                    remedies.append("run 'sfc /scannow' in an Administrator terminal")
                if cascadia_failed:
                    remedies.append("repair Windows Terminal for Cascadia")
                remedy_text = " (and ".join(remedies) + (")" if len(remedies) > 1 else "")
                message = f"Partial restore: {scheduled_count} original fonts scheduled for restore, but {failed_count} font(s) could not be restored ({', '.join(failed_targets)}). Please {remedy_text} to recover missing originals, then restart Windows."
            else:
                message = f"Original Windows fonts ({scheduled_count}/{len(system_files)}) scheduled for restore. Restart Windows now to finish."

            self._emit(progress, 75, "Purging system font caches...")
            cache_warnings = purge_system_font_cache()
            refresh_windows_font_cache()

            # Clean up FontSubstitutes overrides on restore
            try:
                self.registry.remove_font_substitutes()
            except Exception:
                pass

            self._emit(progress, 92, "Saving restore state...")
            state = self.state_store.load_or_empty()
            retained_fonts = {}
            if failed_count > 0:
                old_fonts = state.get("install", {}).get("fonts", {})
                for k, v in old_fonts.items():
                    if v.get("system_filename") in failed_targets:
                        v["status"] = "restore_failed"
                        retained_fonts[k] = v

            if scheduled_count == 0:
                status = "clean" if failed_count == 0 else "partial"
            else:
                status = "pending_reboot_recovery"

            state["install"] = {
                "status": status,
                "fonts": retained_fonts,
                "applied_at": state.get("install", {}).get("applied_at"),
                "restored_at": iso_now(),
            }
            state["last_action"] = {
                "kind": "restore",
                "status": "partial" if failed_count > 0 else "success",
                "timestamp": iso_now(),
                "details": f"Scheduled restore of {scheduled_count} original Microsoft fonts on boot." if scheduled_count > 0 else "System already clean.",
            }
            self.state_store.save(state)

            self._emit(progress, 100, "Font restore complete!" if scheduled_count == 0 else "Font restore scheduled!")
            all_warnings = [
                *pending_cleanup_warnings,
                *purge_warnings,
                *restore_warnings,
                *cache_warnings,
            ]
            return OperationResult(
                True,
                message,
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
                if ("fvar" in built_font or "fvar" in donor_font) and key in ("os2_version", "weight_class", "fs_selection"):
                    continue
                raise RuntimeError(
                    f"Built font identity check failed for {output_path.name}: "
                    f"{key} was {actual[key]!r}, expected {expected_value!r}."
                )
    finally:
        if built_font is not None:
            built_font.close()
        if donor_font is not None:
            donor_font.close()


def _verify_regional_build_output(output_path: Path, donor_path: Path, src_path=None):
    if not output_path.exists() or output_path.stat().st_size < 1_000_000:
        raise RuntimeError(f"Regional hybrid font output missing or truncated: {output_path.name}")

    from fontTools.ttLib import TTCollection, TTFont

    is_ttc = output_path.suffix.lower() == ".ttc"
    built_coll = None
    donor_coll = None
    src_paths = src_path if isinstance(src_path, (list, tuple)) else ([src_path] if src_path else [])
    try:
        if is_ttc:
            built_coll = TTCollection(str(output_path))
            donor_coll = TTCollection(str(donor_path))
            if len(built_coll.fonts) != len(donor_coll.fonts):
                raise RuntimeError(
                    f"Face count mismatch for {output_path.name}: "
                    f"got {len(built_coll.fonts)}, expected {len(donor_coll.fonts)}"
                )
            for i, (b_face, d_face) in enumerate(zip(built_coll.fonts, donor_coll.fonts)):
                if "glyf" not in b_face or "hmtx" not in b_face:
                    raise RuntimeError(f"Face {i} missing core tables in {output_path.name}")
                for tag in ("hdmx", "LTSH", "VDMX", "DSIG"):
                    if tag in b_face:
                        raise RuntimeError(f"Obsolete table {tag} found in face {i} of {output_path.name}")
                
                # Check metric unification: sTypoAscender == hhea.ascent == usWinAscent
                if "OS/2" in b_face and "hhea" in b_face:
                    if not (b_face["OS/2"].sTypoAscender == b_face["hhea"].ascent == b_face["OS/2"].usWinAscent):
                        raise RuntimeError(f"Metric unification mismatch in face {i} of {output_path.name}")

                # Check CJK ideograph outline equality against donor
                b_cmap = b_face.getBestCmap() or {}
                d_cmap = d_face.getBestCmap() or {}
                for cjk_cp in (0x4E00, 0x3042, 0x30A2):
                    if cjk_cp in d_cmap and cjk_cp in b_cmap:
                        d_g = d_face["glyf"][d_cmap[cjk_cp]]
                        b_g = b_face["glyf"][b_cmap[cjk_cp]]
                        if getattr(b_g, "numberOfContours", 0) != getattr(d_g, "numberOfContours", 0):
                            raise RuntimeError(f"CJK ideograph 0x{cjk_cp:X} altered in {output_path.name}")

                # Check Latin digit advances against this face's matching source font
                if src_paths:
                    cur_p = src_paths[min(i, len(src_paths) - 1)]
                    if cur_p and Path(cur_p).exists():
                        cur_font = TTFont(str(cur_p))
                        try:
                            s_cmap = cur_font.getBestCmap() or {}
                            s_hmtx = cur_font["hmtx"]
                            s_upm = cur_font["head"].unitsPerEm or 2048
                            tgt_upm = b_face["head"].unitsPerEm or 2048
                            scale = float(tgt_upm) / float(s_upm)
                            for d in "0123456789":
                                cp = ord(d)
                                if cp in s_cmap and cp in b_cmap:
                                    sw = int(round(s_hmtx[s_cmap[cp]][0] * scale))
                                    tw = b_face["hmtx"][b_cmap[cp]][0]
                                    if abs(sw - tw) > 1:
                                        raise RuntimeError(f"Digit {d} advance width mismatch in face {i} of {output_path.name}")
                        finally:
                            cur_font.close()
        else:
            built_font = TTFont(str(output_path))
            donor_font = TTFont(str(donor_path))
            try:
                if "glyf" not in built_font or "hmtx" not in built_font:
                    raise RuntimeError(f"Missing core tables in {output_path.name}")
                for tag in ("hdmx", "LTSH", "VDMX", "DSIG"):
                    if tag in built_font:
                        raise RuntimeError(f"Obsolete table {tag} found in {output_path.name}")
                
                if "OS/2" in built_font and "hhea" in built_font:
                    if not (built_font["OS/2"].sTypoAscender == built_font["hhea"].ascent == built_font["OS/2"].usWinAscent):
                        raise RuntimeError(f"Metric unification mismatch in {output_path.name}")

                b_cmap = built_font.getBestCmap() or {}
                d_cmap = donor_font.getBestCmap() or {}
                for cjk_cp in (0x4E00, 0x3042, 0x30A2):
                    if cjk_cp in d_cmap and cjk_cp in b_cmap:
                        d_g = donor_font["glyf"][d_cmap[cjk_cp]]
                        b_g = built_font["glyf"][b_cmap[cjk_cp]]
                        if getattr(b_g, "numberOfContours", 0) != getattr(d_g, "numberOfContours", 0):
                            raise RuntimeError(f"CJK ideograph 0x{cjk_cp:X} altered in {output_path.name}")

                if src_paths:
                    cur_p = src_paths[0]
                    if cur_p and Path(cur_p).exists():
                        cur_font = TTFont(str(cur_p))
                        try:
                            s_cmap = cur_font.getBestCmap() or {}
                            s_hmtx = cur_font["hmtx"]
                            s_upm = cur_font["head"].unitsPerEm or 2048
                            tgt_upm = built_font["head"].unitsPerEm or 2048
                            scale = float(tgt_upm) / float(s_upm)
                            for d in "0123456789":
                                cp = ord(d)
                                if cp in s_cmap and cp in b_cmap:
                                    sw = int(round(s_hmtx[s_cmap[cp]][0] * scale))
                                    tw = built_font["hmtx"][b_cmap[cp]][0]
                                    if abs(sw - tw) > 1:
                                        raise RuntimeError(f"Digit {d} advance width mismatch in {output_path.name}")
                        finally:
                            cur_font.close()
            finally:
                built_font.close()
                donor_font.close()
    finally:
        if built_coll is not None:
            built_coll.close()
        if donor_coll is not None:
            donor_coll.close()


def _build_one_regional(job):
    from font_generation import build_hybrid_regional_font
    reg_file, donor_path_s, src_paths_s, out_path_s = job
    donor_path = Path(donor_path_s)
    src_paths = [Path(p) for p in src_paths_s]
    out_path = Path(out_path_s)
    build_hybrid_regional_font(src_paths, donor_path, out_path)
    _verify_regional_build_output(out_path, donor_path, src_paths)
    return reg_file, hash_file(out_path)


def build_artifacts(workflow, entries, stage_dir, build_warnings=None, *, include_regional: bool = True, progress=None):
    from operation_files import find_original_font_backup
    artifacts = {}
    mono_regular_entry = None
    for entry in entries:
        if entry.weight == "consolas_regular":
            mono_regular_entry = entry

        segoe_path = find_original_font_backup(workflow, entry.system_filename) or (workflow.identity_fonts_root / entry.system_filename)
        output_path = stage_dir / entry.system_filename

        if entry.system_filename.lower() == "seguivar.ttf":
            from font_generation import build_variable_font
            build_variable_font(entry.source_path, segoe_path, output_path)
        else:
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

    if mono_regular_entry is not None:
        from font_detection import inspect_font
        from settings import get_existing_mono_companions
        try:
            mono_meta = inspect_font(mono_regular_entry.source_path)
            is_mono = getattr(mono_meta, "is_monospace", False) or mono_regular_entry.source_label == "manual"
        except Exception:
            is_mono = True

        if is_mono:
            companions = get_existing_mono_companions(workflow.identity_fonts_root)
            for companion_file, companion_reg_name in companions.items():
                companion_sys_path = find_original_font_backup(workflow, companion_file)
                if not companion_sys_path or not companion_sys_path.exists():
                    if build_warnings is not None:
                        build_warnings.append(f"Note: Companion font {companion_file} skipped: original backup not found.")
                    continue
                companion_out_path = stage_dir / companion_file
                build_font(mono_regular_entry.source_path, companion_sys_path, companion_out_path)
                _verify_build_output(companion_out_path, companion_sys_path)
                companion_key = f"mono_companion_{companion_file.lower().replace('.', '_')}"
                artifacts[companion_key] = {
                    "weight": companion_key,
                    "registry_name": companion_reg_name,
                    "system_filename": companion_file,
                    "generated_filename": companion_file,
                    "source_path": str(mono_regular_entry.source_path),
                    "family_name": mono_regular_entry.family_name,
                    "full_name": mono_regular_entry.full_name,
                    "staged_path": str(companion_out_path),
                    "hash": hash_file(companion_out_path),
                }

    entries_by_weight = {entry.weight: entry for entry in entries}
    regular_entry = entries_by_weight.get("regular")
    bold_entry = entries_by_weight.get("bold") or regular_entry

    # Build UI companion fonts (e.g. Tahoma, Tahoma Bold for Delphi / legacy Win32 apps)
    from settings import get_existing_ui_companions
    ui_companions = get_existing_ui_companions(workflow.identity_fonts_root)
    if regular_entry is not None and ui_companions:
        for companion_file, companion_reg_name in ui_companions.items():
            is_bold = "bd" in companion_file.lower()
            src_entry = bold_entry if is_bold else regular_entry
            companion_sys_path = find_original_font_backup(workflow, companion_file)
            if not companion_sys_path or not companion_sys_path.exists():
                if build_warnings is not None:
                    build_warnings.append(f"Note: Companion font {companion_file} skipped: original backup not found.")
                continue
            companion_out_path = stage_dir / companion_file
            build_font(src_entry.source_path, companion_sys_path, companion_out_path)
            _verify_build_output(companion_out_path, companion_sys_path)
            companion_key = f"ui_companion_{companion_file.lower().replace('.', '_')}"
            artifacts[companion_key] = {
                "weight": companion_key,
                "registry_name": companion_reg_name,
                "system_filename": companion_file,
                "generated_filename": companion_file,
                "source_path": str(src_entry.source_path),
                "family_name": src_entry.family_name,
                "full_name": src_entry.full_name,
                "staged_path": str(companion_out_path),
                "hash": hash_file(companion_out_path),
            }

    # Build regional hybrid fonts (Tier 1 CJK Latin surgery)
    from settings import get_existing_regional_targets
    from operation_files import find_original_font_backup
    from font_generation import build_hybrid_regional_font

    regional_targets = get_existing_regional_targets(workflow.identity_fonts_root)

    if include_regional and regular_entry is not None and regional_targets:
        jobs = []
        meta_by_reg = {}
        for reg_file, pref_weight in regional_targets.items():
            donor_path = find_original_font_backup(workflow, reg_file)
            if not donor_path or not donor_path.exists():
                if build_warnings is not None:
                    build_warnings.append(f"Regional font {reg_file} skipped: Pristine backup not found in backup store or WinSxS.")
                continue

            if isinstance(pref_weight, (list, tuple)):
                src_paths = [
                    (entries_by_weight.get(w) or entries_by_weight.get("semibold") or regular_entry).source_path
                    if w == "medium" else (entries_by_weight.get(w) or regular_entry).source_path
                    for w in pref_weight
                ]
                src_entry = entries_by_weight.get(pref_weight[0]) or regular_entry
            else:
                src_entry = entries_by_weight.get(pref_weight) or regular_entry
                src_paths = [src_entry.source_path]

            out_path = stage_dir / reg_file
            meta_by_reg[reg_file] = (src_entry, out_path)
            jobs.append((reg_file, str(donor_path), [str(p) for p in src_paths], str(out_path)))

        if jobs:
            max_workers = min(4, os.cpu_count() or 4)
            if len(jobs) > 1 and max_workers > 1:
                from concurrent.futures import ProcessPoolExecutor, as_completed
                with ProcessPoolExecutor(max_workers=max_workers) as pool:
                    futures = {pool.submit(_build_one_regional, job): job[0] for job in jobs}
                    for i, fut in enumerate(as_completed(futures), 1):
                        reg_file = futures[fut]
                        src_entry, out_path = meta_by_reg[reg_file]
                        try:
                            _, digest = fut.result()
                            reg_key = f"regional_{reg_file.lower().replace('.', '_')}"
                            artifacts[reg_key] = {
                                "weight": reg_key,
                                "registry_name": None,
                                "system_filename": reg_file,
                                "generated_filename": reg_file,
                                "source_path": str(src_entry.source_path),
                                "family_name": src_entry.family_name,
                                "full_name": src_entry.full_name,
                                "staged_path": str(out_path),
                                "hash": digest,
                            }
                        except Exception as exc:
                            if build_warnings is not None:
                                build_warnings.append(f"Regional font {reg_file} skipped: {exc}")
                        if progress and hasattr(workflow, "_emit"):
                            workflow._emit(progress, 30 + int(45 * i / len(jobs)), f"Built {reg_file} ({i}/{len(jobs)})")
            else:
                for i, job in enumerate(jobs, 1):
                    reg_file = job[0]
                    src_entry, out_path = meta_by_reg[reg_file]
                    try:
                        _, digest = _build_one_regional(job)
                        reg_key = f"regional_{reg_file.lower().replace('.', '_')}"
                        artifacts[reg_key] = {
                            "weight": reg_key,
                            "registry_name": None,
                            "system_filename": reg_file,
                            "generated_filename": reg_file,
                            "source_path": str(src_entry.source_path),
                            "family_name": src_entry.family_name,
                            "full_name": src_entry.full_name,
                            "staged_path": str(out_path),
                            "hash": digest,
                        }
                    except Exception as exc:
                        if build_warnings is not None:
                            build_warnings.append(f"Regional font {reg_file} skipped: {exc}")
                    if progress and hasattr(workflow, "_emit"):
                        workflow._emit(progress, 30 + int(45 * i / len(jobs)), f"Built {reg_file} ({i}/{len(jobs)})")

    return artifacts
