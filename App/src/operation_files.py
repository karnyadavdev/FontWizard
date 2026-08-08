import ctypes
import json
import shutil
import uuid
import winreg
from pathlib import Path

from settings import default_registry_targets
from app_state import hash_file, iso_now


_MOVEFILE_DELAY_UNTIL_REBOOT = 0x4
_MOVEFILE_REPLACE_EXISTING = 0x1

_kernel32 = ctypes.windll.kernel32
_MoveFileExW = _kernel32.MoveFileExW
_MoveFileExW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p, ctypes.c_uint]
_MoveFileExW.restype = ctypes.c_bool


_SESSION_MANAGER_SUBKEY = r"SYSTEM\CurrentControlSet\Control\Session Manager"
_PENDING_RENAME_VALUE = "PendingFileRenameOperations"
_OLD_FILE_SUFFIX = ".old"
_MANAGED_SUFFIXES = ("_mod.ttf",)


def stage_persistent_operation_file(workflow, src, dst, suffix):
    workflow.paths.ensure_runtime_dirs()
    staged = workflow.paths.pending_ops_root / f"{dst.stem}_{uuid.uuid4().hex[:8]}{suffix}{dst.suffix}"
    shutil.copy2(src, staged)
    return staged


def cleanup_orphaned_pending_ops(workflow) -> tuple[list[str], bool]:
    referenced = _read_pending_rename_sources()
    warnings = []
    is_pending = False
    for path in workflow.paths.pending_ops_root.glob("*_pending_replace.*"):
        if str(path).lower() in referenced:
            is_pending = True
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            warnings.append(f"Could not remove stale pending operation {path}: {exc}")
    return warnings, is_pending


def cleanup_font_directory_artifacts(workflow, protected_files=None) -> tuple[list[str], bool]:
    referenced = _read_pending_rename_sources()
    protected = {str(name).lower() for name in (protected_files or []) if name}
    warnings = []
    is_pending = False
    managed_stems = {Path(name).stem.lower() for name in workflow._system_font_files()}

    for path in workflow.active_fonts_root.iterdir():
        if not path.is_file():
            continue
        if path.name.lower() in protected:
            continue
        if not _is_cleanup_candidate(path.name, managed_stems):
            continue
        if str(path).lower() in referenced:
            is_pending = True
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if schedule_delete_on_reboot(path):
                warnings.append(f"Removal scheduled for reboot: {path}")
                is_pending = True
            else:
                warnings.append(f"Could not remove stale font artifact {path}: {exc}")
    return warnings, is_pending


def _read_pending_rename_sources() -> set[str]:
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _SESSION_MANAGER_SUBKEY,
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        ) as key:
            values, _ = winreg.QueryValueEx(key, _PENDING_RENAME_VALUE)
    except OSError:
        return set()

    if not isinstance(values, list):
        return set()

    entries = set()
    for value in values[::2]:
        normalized = _normalize_pending_path(value)
        if normalized:
            entries.add(normalized)
    return entries


def _normalize_pending_path(value):
    if not value:
        return None

    normalized = value.replace("/", "\\").strip()
    for prefix in ("\\??\\", "!", "\\\\?\\"):
        if normalized.startswith(prefix):
            normalized = normalized[len(prefix):]
    return normalized.lower()


def _is_cleanup_candidate(filename, managed_stems):
    lower = filename.lower()
    stem = Path(lower).stem
    return any(
        (lower.endswith(_OLD_FILE_SUFFIX) and stem.startswith(f"{managed_stem}_"))
        or (lower.startswith(f"{managed_stem}_fontwizard"))
        or (lower.startswith(f"{managed_stem}_pending_replace"))
        for managed_stem in managed_stems
    )


def schedule_delete_on_reboot(path):
    return bool(_MoveFileExW(str(path), None, _MOVEFILE_DELAY_UNTIL_REBOOT))


def schedule_replace_on_reboot(workflow, src, dst):
    staged_src = stage_persistent_operation_file(workflow, src, dst, "_pending_replace")
    ok = _MoveFileExW(
        str(staged_src),
        str(dst),
        _MOVEFILE_DELAY_UNTIL_REBOOT | _MOVEFILE_REPLACE_EXISTING,
    )
    if not ok:
        staged_src.unlink(missing_ok=True)
        return False
    return True


def force_copy(workflow, src, dst):
    try:
        shutil.copy2(src, dst)
        return False
    except OSError:
        if not dst.exists():
            raise

    old_name = dst.parent / f"{dst.stem}_{uuid.uuid4().hex[:8]}.old"
    try:
        dst.rename(old_name)
    except OSError:
        pass
    else:
        try:
            shutil.copy2(src, dst)
        except OSError:
            if not dst.exists():
                try:
                    old_name.rename(dst)
                except OSError:
                    pass
            raise
        schedule_delete_on_reboot(old_name)
        return False

    if schedule_replace_on_reboot(workflow, src, dst):
        return True

    raise OSError(
        f"Cannot write to {dst} - the file is locked by another process "
        f"and all fallback strategies have been exhausted."
    )


def install_transaction(workflow, artifacts: dict[str, dict], previous_registry: dict[str, str | None], rollback_dir: Path) -> dict:
    targets = default_registry_targets()
    for artifact in artifacts.values():
        targets[artifact["registry_name"]] = artifact["generated_filename"]

    fonts_manifest = {}
    deferred_fonts = []
    warnings = []

    workflow.registry.write_targets(targets)
    try:
        workflow.registry.ensure_font_substitutes()
    except Exception as exc:
        warnings.append(f"Could not update MS Shell Dlg 2 registry substitute: {exc}")

    applied = workflow.registry.read_targets(list(targets.keys()))
    if applied != targets:
        raise RuntimeError("Registry verification failed before installing managed fonts.")

    for artifact in artifacts.values():
        staged_path = Path(artifact["staged_path"])
        system_filename = artifact["system_filename"]
        managed_path = workflow.paths.managed_font_root / artifact["generated_filename"]
        active_path = workflow.active_fonts_root / artifact["generated_filename"]

        prepare_rollback_file(active_path, rollback_dir)
        shutil.copy2(staged_path, managed_path)
        _verify_hash(managed_path, artifact["hash"], "managed")
        
        deferred = force_copy(workflow, staged_path, active_path)
        if deferred:
            deferred_fonts.append(artifact["generated_filename"])
        else:
            _verify_hash(active_path, artifact["hash"], "installed")

        fonts_manifest[artifact["weight"]] = {
            "source_path": artifact["source_path"],
            "family_name": artifact["family_name"],
            "full_name": artifact["full_name"],
            "system_filename": system_filename,
            "generated_filename": artifact["generated_filename"],
            "managed_path": str(managed_path),
            "active_path": str(active_path),
            "sha256": artifact["hash"],
        }

    cleanup_warnings = cleanup_stale_previous_fonts(workflow, previous_registry, fonts_manifest)
    warnings.extend(cleanup_warnings[0])
    if deferred_fonts:
        for font_name in deferred_fonts:
            warnings.append(f"Font replacement scheduled for reboot: {workflow.active_fonts_root / font_name}")
        warnings.append(
            "Some font files are queued for replacement on reboot. Restart Windows before applying another font."
        )
    return {
        "status": "applied",
        "registry_targets": targets,
        "fonts": fonts_manifest,
        "deferred_fonts": deferred_fonts,
        "warnings": warnings,
        "previous_registry": previous_registry,
        "applied_at": iso_now(),
        "restored_at": None,
    }


def _verify_hash(path: Path, expected_hash: str, label: str) -> None:
    if not path.exists():
        raise RuntimeError(f"Expected {label} font file does not exist: {path.name}")
    actual_hash = hash_file(path)
    if actual_hash != expected_hash:
        raise RuntimeError(
            f"Installed {label} font hash mismatch for {path.name}: "
            f"{actual_hash} != {expected_hash}"
        )


def rollback_status_path(active_path: Path, rollback_dir: Path) -> Path:
    return rollback_dir / f"{active_path.name}.rollback.json"


def write_rollback_status(active_path: Path, rollback_dir: Path, payload: dict) -> None:
    path = rollback_status_path(active_path, rollback_dir)
    path.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")


def read_rollback_status(active_path: Path, rollback_dir: Path) -> dict:
    path = rollback_status_path(active_path, rollback_dir)
    if not path.exists():
        return {"status": "unknown"}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"status": "unknown"}


def prepare_rollback_file(active_path: Path, rollback_dir: Path) -> None:
    if not active_path.exists():
        write_rollback_status(active_path, rollback_dir, {"status": "missing"})
        return

    backup_path = rollback_dir / active_path.name
    try:
        shutil.copy2(active_path, backup_path)
    except OSError as exc:
        raise RuntimeError(f"Could not capture rollback backup for {active_path.name}: {exc}") from exc

    write_rollback_status(
        active_path,
        rollback_dir,
        {"status": "backed_up", "backup_path": str(backup_path)},
    )


def rollback(workflow, previous_registry, artifacts, rollback_dir):
    workflow.registry.write_targets(previous_registry)

    for artifact in artifacts.values():
        active_path = workflow.active_fonts_root / artifact["generated_filename"]
        managed_path = workflow.paths.managed_font_root / artifact["generated_filename"]
        status = read_rollback_status(active_path, rollback_dir)
        state = status.get("status")

        if state == "backed_up":
            backup_path = Path(status.get("backup_path", ""))
            if backup_path.exists():
                try:
                    force_copy(workflow, backup_path, active_path)
                except OSError:
                    pass
        elif state == "missing":
            try:
                active_path.unlink(missing_ok=True)
            except OSError:
                schedule_delete_on_reboot(active_path)

        try:
            managed_path.unlink(missing_ok=True)
        except OSError:
            schedule_delete_on_reboot(managed_path)


def cleanup_stale_previous_fonts(workflow, previous_registry: dict[str, str | None], fonts_manifest: dict[str, dict]) -> tuple[list[str], bool]:
    current_files = {font["generated_filename"] for font in fonts_manifest.values()}
    warnings = []
    is_pending = False
    
    stale_paths = set()
    for root in (workflow.paths.managed_font_root, workflow.active_fonts_root):
        if not root.exists():
            continue
        for path in root.iterdir():
            if not path.is_file():
                continue
            name_lower = path.name.lower()
            if "_fontwizard" not in name_lower and not any(name_lower.endswith(s) for s in _MANAGED_SUFFIXES):
                continue
            if path.name in current_files:
                continue
            stale_paths.add(path)

    for path in stale_paths:
        try:
            path.unlink(missing_ok=True)
        except OSError as exc:
            if schedule_delete_on_reboot(path):
                warnings.append(f"Removal scheduled for reboot: {path}")
                is_pending = True
            else:
                warnings.append(f"Could not remove stale managed font {path}: {exc}")
    return warnings, is_pending


def cleanup_managed_fonts(workflow, previous_registry: dict[str, str | None], state: dict) -> tuple[list[str], bool]:
    managed_files = set()
    is_pending = False
    install_data = state.get("install") or {}
    for info in install_data.get("fonts", {}).values():
        managed_path = info.get("managed_path", "")
        active_path = info.get("active_path", "")
        if managed_path:
            managed_files.add(Path(managed_path))
        if active_path and _is_managed_extra_font(active_path):
            managed_files.add(Path(active_path))

    for filename in previous_registry.values():
        if not filename:
            continue
        lower = filename.lower()
        if "_fontwizard" in lower or any(lower.endswith(s) for s in _MANAGED_SUFFIXES):
            managed_files.add(workflow.active_fonts_root / filename)

    warnings = []
    for file_path in managed_files:
        if file_path and file_path.exists():
            try:
                file_path.unlink(missing_ok=True)
            except OSError as exc:
                if schedule_delete_on_reboot(file_path):
                    warnings.append(f"Removal scheduled for reboot: {file_path}")
                    is_pending = True
                else:
                    warnings.append(f"Could not remove {file_path}: {exc}")
                    
    pending_warnings, pending_reboot = cleanup_orphaned_pending_ops(workflow)
    warnings.extend(pending_warnings)
    if pending_reboot:
        is_pending = True
    
    return warnings, is_pending


def _is_managed_extra_font(path_value):
    lower = Path(path_value).name.lower()
    return "_fontwizard" in lower or any(lower.endswith(s) for s in _MANAGED_SUFFIXES)
