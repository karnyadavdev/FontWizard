import ctypes
import json
import os
import shutil
import subprocess
import uuid
import winreg
from ctypes import wintypes
from pathlib import Path

from settings import default_registry_targets
from app_state import hash_file, iso_now
from winsxs import find_winsxs_font, is_authentic_font, profile


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

_ACL_FLAGS = 0
if os.name == "nt":
    _ACL_FLAGS = subprocess.CREATE_NO_WINDOW

_SE_FILE_OBJECT = 0x1
_OWNER_SECURITY_INFORMATION = 0x1
_DACL_SECURITY_INFORMATION = 0x4
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_UNPROTECTED_DACL_SECURITY_INFORMATION = 0x40000000

_advapi32 = ctypes.windll.advapi32
_advapi32.GetNamedSecurityInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.LPVOID),
]
_advapi32.GetNamedSecurityInfoW.restype = wintypes.DWORD
_advapi32.LookupAccountSidW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.LPVOID,
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPWSTR,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.POINTER(wintypes.DWORD),
]
_advapi32.LookupAccountSidW.restype = wintypes.BOOL
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.DWORD),
]
_advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = wintypes.BOOL
_advapi32.MakeAbsoluteSD.argtypes = [
    wintypes.LPVOID,
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.DWORD),
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.DWORD),
]
_advapi32.MakeAbsoluteSD.restype = wintypes.BOOL
_advapi32.GetSecurityDescriptorDacl.argtypes = [
    wintypes.LPVOID,
    ctypes.POINTER(wintypes.BOOL),
    ctypes.POINTER(wintypes.LPVOID),
    ctypes.POINTER(wintypes.BOOL),
]
_advapi32.GetSecurityDescriptorDacl.restype = wintypes.BOOL
_advapi32.SetNamedSecurityInfoW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.LPVOID,
    wintypes.LPVOID,
]
_advapi32.SetNamedSecurityInfoW.restype = wintypes.DWORD
_kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
_kernel32.LocalFree.restype = wintypes.HLOCAL


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


def atomic_replace(src, dst) -> None:
    src = Path(src)
    dst = Path(dst)
    if not dst.parent.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
    temp = dst.parent / f".{dst.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        shutil.copy2(src, temp)
    except OSError:
        temp.unlink(missing_ok=True)
        raise
    try:
        os.replace(temp, dst)
    except OSError:
        temp.unlink(missing_ok=True)
        raise
    _cancel_pending_rename_ops(dst)


def _get_owner_name(path: Path):
    try:
        owner_sid = wintypes.LPVOID()
        descriptor = wintypes.LPVOID()
        rc = _advapi32.GetNamedSecurityInfoW(
            str(path),
            _SE_FILE_OBJECT,
            _OWNER_SECURITY_INFORMATION,
            ctypes.byref(owner_sid),
            None,
            None,
            None,
            ctypes.byref(descriptor),
        )
        if rc != 0 or not owner_sid:
            return None
        name = ctypes.create_unicode_buffer(256)
        domain = ctypes.create_unicode_buffer(256)
        name_size = wintypes.DWORD(256)
        domain_size = wintypes.DWORD(256)
        sid_type = wintypes.DWORD()
        if not _advapi32.LookupAccountSidW(
            None,
            owner_sid,
            name,
            ctypes.byref(name_size),
            domain,
            ctypes.byref(domain_size),
            ctypes.byref(sid_type),
        ):
            return None
        return f"{domain.value}\\{name.value}" if domain.value else name.value
    except Exception:
        return None
    finally:
        try:
            _kernel32.LocalFree(descriptor)
        except Exception:
            pass


def snapshot_file_acl(path: Path, backup_root: Path, system_filename: str):
    owner_name = _get_owner_name(path)
    sda_path = backup_root / f"{system_filename}.sda"
    try:
        result = subprocess.run(
            ["icacls.exe", str(path), "/save", str(sda_path)],
            capture_output=True,
            timeout=30,
            creationflags=_ACL_FLAGS,
        )
        if result.returncode != 0 or not sda_path.exists():
            sda_path.unlink(missing_ok=True)
            sda_path = None
    except (OSError, subprocess.SubprocessError):
        sda_path = None

    metadata = backup_root / f"{system_filename}.acl.json"
    try:
        metadata.write_text(
            json.dumps(
                {"owner_name": owner_name, "sda": sda_path.name if sda_path else None},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return owner_name, sda_path


def _set_dacl_ctypes(path: Path, dacl_sddl: str, protected: bool) -> int:
    descriptor = wintypes.LPVOID()
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        dacl_sddl, 1, ctypes.byref(descriptor), None
    ):
        return 1306
    try:
        abs_size = wintypes.DWORD(0)
        dacl_size = wintypes.DWORD(0)
        sacl_size = wintypes.DWORD(0)
        owner_size = wintypes.DWORD(0)
        group_size = wintypes.DWORD(0)
        _advapi32.MakeAbsoluteSD(
            descriptor.value,
            None,
            ctypes.byref(abs_size),
            None,
            ctypes.byref(dacl_size),
            None,
            ctypes.byref(sacl_size),
            None,
            ctypes.byref(owner_size),
            None,
            ctypes.byref(group_size),
        )
        abs_buffer = ctypes.create_string_buffer(max(abs_size.value, 1))
        dacl_buffer = ctypes.create_string_buffer(max(dacl_size.value, 1))
        sacl_buffer = ctypes.create_string_buffer(max(sacl_size.value, 1))
        owner_buffer = ctypes.create_string_buffer(max(owner_size.value, 1))
        group_buffer = ctypes.create_string_buffer(max(group_size.value, 1))
        if not _advapi32.MakeAbsoluteSD(
            descriptor.value,
            abs_buffer,
            ctypes.byref(abs_size),
            dacl_buffer,
            ctypes.byref(dacl_size),
            sacl_buffer,
            ctypes.byref(sacl_size),
            owner_buffer,
            ctypes.byref(owner_size),
            group_buffer,
            ctypes.byref(group_size),
        ):
            return 1307
        has_dacl = wintypes.BOOL()
        dacl_ptr = wintypes.LPVOID()
        dacl_defaulted = wintypes.BOOL()
        if not _advapi32.GetSecurityDescriptorDacl(
            abs_buffer, ctypes.byref(has_dacl), ctypes.byref(dacl_ptr), ctypes.byref(dacl_defaulted)
        ):
            return 1308
        if not has_dacl.value or not dacl_ptr:
            return 1309
        info = _DACL_SECURITY_INFORMATION
        info |= _PROTECTED_DACL_SECURITY_INFORMATION if protected else _UNPROTECTED_DACL_SECURITY_INFORMATION
        return _advapi32.SetNamedSecurityInfoW(
            str(path),
            _SE_FILE_OBJECT,
            info,
            None,
            None,
            dacl_ptr,
            None,
        )
    finally:
        _kernel32.LocalFree(descriptor)


def _restore_dacl(file_path: Path, sda_path: Path) -> str:
    try:
        raw = sda_path.read_bytes()
        if raw.startswith(b"\xff\xfe"):
            raw = raw[2:]
        elif raw.startswith(b"\xfe\xff"):
            raw = raw[2:]
        text = raw.decode("utf-16-le")
    except (OSError, UnicodeError):
        return f"Could not read the ACL snapshot for {file_path.name}."

    dacl_sddl = next((line for line in text.split("\r\n") if line.startswith("D:")), None)
    if not dacl_sddl:
        return f"No DACL found in the ACL snapshot for {file_path.name}."

    protected = "P" in dacl_sddl.split("(", 1)[0]
    result = _set_dacl_ctypes(file_path, dacl_sddl, protected)
    if result != 0:
        return f"Could not restore the original file permissions for {file_path.name} (error {result})."
    return ""


def restore_file_acl(file_path: Path, backup_root: Path, system_filename: str, final=False) -> list[str]:
    warnings = []
    metadata = backup_root / f"{system_filename}.acl.json"
    if not metadata.exists():
        return warnings
    try:
        info = json.loads(metadata.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return warnings

    owner_name = info.get("owner_name")
    if owner_name:
        try:
            result = subprocess.run(
                ["icacls.exe", str(file_path), "/setowner", owner_name],
                capture_output=True,
                timeout=30,
                creationflags=_ACL_FLAGS,
            )
            if result.returncode != 0:
                warnings.append(f"Could not restore the original owner for {file_path.name}.")
        except (OSError, subprocess.SubprocessError):
            warnings.append(f"Could not restore the original owner for {file_path.name}.")

    sda_name = info.get("sda")
    if sda_name:
        error = _restore_dacl(file_path, backup_root / sda_name)
        if error:
            warnings.append(error)

    if final and not warnings:
        for sidecar in (metadata, backup_root / sda_name) if sda_name else (metadata,):
            try:
                sidecar.unlink(missing_ok=True)
            except OSError:
                pass
    return warnings


def _cancel_pending_rename_ops(dst) -> None:
    target_norm = _normalize_pending_path(str(dst))
    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _SESSION_MANAGER_SUBKEY,
            0,
            winreg.KEY_READ | winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            values, _ = winreg.QueryValueEx(key, _PENDING_RENAME_VALUE)
    except OSError:
        return
    if not isinstance(values, list) or not values:
        return

    kept = []
    removed = False
    for index in range(0, len(values), 2):
        pair = values[index:index + 2]
        dest = pair[1] if len(pair) > 1 else None
        if dest and _normalize_pending_path(dest) == target_norm:
            removed = True
            continue
        kept.extend(pair)
    if not removed:
        return

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            _SESSION_MANAGER_SUBKEY,
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            if kept:
                winreg.SetValueEx(key, _PENDING_RENAME_VALUE, 0, winreg.REG_MULTI_SZ, kept)
            else:
                winreg.DeleteValue(key, _PENDING_RENAME_VALUE)
    except OSError:
        pass


def schedule_replace_on_reboot(workflow, src, dst):
    _cancel_pending_rename_ops(dst)
    staged_src = stage_persistent_operation_file(workflow, src, dst, "_pending_replace")
    ok = _MoveFileExW(
        str(staged_src),
        str(dst),
        _MOVEFILE_DELAY_UNTIL_REBOOT | _MOVEFILE_REPLACE_EXISTING,
    )
    if not ok:
        staged_src.unlink(missing_ok=True)
        return None
    return staged_src


def force_copy(workflow, src, dst):
    try:
        atomic_replace(src, dst)
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
            atomic_replace(src, dst)
        except OSError:
            try:
                dst.unlink(missing_ok=True)
            except OSError:
                pass
            try:
                old_name.rename(dst)
            except OSError:
                pass
            raise
        schedule_delete_on_reboot(old_name)
        return False

    if schedule_replace_on_reboot(workflow, src, dst) is not None:
        return True

    raise OSError(
        f"Cannot write to {dst} - the file is locked by another process "
        f"and all fallback strategies have been exhausted."
    )


def install_transaction(workflow, artifacts: dict[str, dict], previous_registry: dict[str, str | None], rollback_dir: Path, previous_substitutes: dict[str, str | None] | None = None) -> dict:
    targets = default_registry_targets()
    for artifact in artifacts.values():
        targets[artifact["registry_name"]] = artifact["generated_filename"]

    for name in list(targets):
        if name in artifacts:
            continue
        if not (workflow.active_fonts_root / targets[name]).exists():
            targets.pop(name, None)

    fonts_manifest = {}
    deferred_fonts = []
    warnings = []

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

        fonts_manifest[artifact["registry_name"]] = {
            "source_path": artifact["source_path"],
            "family_name": artifact["family_name"],
            "full_name": artifact["full_name"],
            "system_filename": system_filename,
            "generated_filename": artifact["generated_filename"],
            "managed_path": str(managed_path),
            "active_path": str(active_path),
            "sha256": artifact["hash"],
        }

    workflow.registry.write_targets(targets)
    try:
        workflow.registry.ensure_font_substitutes()
    except Exception as exc:
        warnings.append(f"Could not update MS Shell Dlg 2 registry substitute: {exc}")

    applied = workflow.registry.read_targets(list(targets.keys()))
    if applied != targets:
        raise RuntimeError("Registry verification failed after installing managed fonts.")

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
        "previous_registry": sanitize_previous_registry(previous_registry),
        "previous_substitutes": previous_substitutes,
        "applied_at": iso_now(),
        "restored_at": None,
    }


def sanitize_previous_registry(previous_registry: dict[str, str | None]) -> dict[str, str | None]:
    defaults = default_registry_targets()
    cleaned = {}
    for name, filename in previous_registry.items():
        if not filename:
            cleaned[name] = None
            continue
        lower = filename.lower()
        if "_fontwizard" in lower or any(lower.endswith(s) for s in _MANAGED_SUFFIXES):
            cleaned[name] = defaults.get(name, filename)
        else:
            cleaned[name] = filename
    return cleaned


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


def rollback(workflow, previous_registry, artifacts, rollback_dir, previous_substitutes=None):
    workflow.registry.write_targets(previous_registry)
    if previous_substitutes:
        try:
            workflow.registry.write_substitutes(previous_substitutes)
        except OSError:
            pass

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

    try:
        restore_original_fonts(workflow)
    except Exception:
        pass


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


def cleanup_managed_fonts(workflow, previous_registry: dict[str, str | None], state: dict, keep_system_filenames=None) -> tuple[list[str], bool]:
    keep_system_filenames = keep_system_filenames or set()
    managed_files = set()
    kept_paths = set()
    is_pending = False
    install_data = state.get("install") or {}
    for info in install_data.get("fonts", {}).values():
        managed_path = info.get("managed_path", "")
        active_path = info.get("active_path", "")
        if info.get("system_filename") in keep_system_filenames:
            if managed_path:
                kept_paths.add(str(Path(managed_path).resolve()))
            if active_path:
                kept_paths.add(str(Path(active_path).resolve()))
            continue
        if managed_path:
            managed_files.add(Path(managed_path))
        if active_path and _is_managed_extra_font(active_path):
            managed_files.add(Path(active_path))

    for filename in previous_registry.values():
        if not filename:
            continue
        lower = filename.lower()
        if "_fontwizard" in lower or any(lower.endswith(s) for s in _MANAGED_SUFFIXES):
            path = workflow.active_fonts_root / filename
            if str(path.resolve()) in kept_paths:
                continue
            managed_files.add(path)

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


def _default_system_files() -> list[str]:
    return list(dict.fromkeys(default_registry_targets().values()))


def _grant_owner_write(path: Path) -> None:
    subprocess.run(
        ["takeown", "/f", str(path)],
        capture_output=True,
        creationflags=_ACL_FLAGS,
    )
    subprocess.run(
        ["icacls", str(path), "/grant", "*S-1-5-32-544:(F)"],
        capture_output=True,
        creationflags=_ACL_FLAGS,
    )


def _apply_log(workflow, message: str) -> None:
    try:
        workflow.paths.ensure_runtime_dirs()
        with (workflow.paths.log_root / "apply.log").open("a", encoding="utf-8") as handle:
            handle.write(f"{iso_now()} {message}\n")
    except OSError:
        pass


def _emit_progress(workflow, progress, value, message) -> None:
    emitter = getattr(workflow, "_emit", None)
    if progress and callable(emitter):
        emitter(progress, value, message)


def _clone_dacl_from_reference(workflow, dst: Path, system_file: str) -> list[str]:
    reference = workflow.active_fonts_root / "arial.ttf"
    if not reference.exists():
        return [
            f"Could not restore the original file permissions for {system_file} "
            "(reference font arial.ttf is unavailable)."
        ]
    acl_dir = workflow.paths.temp_root / "acl-clone"
    try:
        workflow.paths.ensure_runtime_dirs()
        acl_dir.mkdir(parents=True, exist_ok=True)
        snapshot_file_acl(reference, acl_dir, reference.stem)
        return restore_file_acl(dst, acl_dir, reference.stem)
    except OSError:
        return [f"Could not restore the original file permissions for {system_file}."]


def _restore_from_store(workflow, system_file: str, dst: Path, store_file, restored, deferred, missing, warnings, source_note) -> None:
    _apply_log(workflow, f"{system_file}: restoring from component store {store_file}")
    try:
        _grant_owner_write(dst)
        atomic_replace(store_file, dst)
    except OSError as exc:
        staged = schedule_replace_on_reboot(workflow, store_file, dst)
        if staged is not None:
            deferred.add(system_file)
            warnings.append(
                f"Font {system_file} is locked and will be restored from the "
                "Windows component store after restart."
            )
            _apply_log(workflow, f"{system_file}: store restore scheduled for reboot")
        else:
            warnings.append(f"Could not restore original font {system_file}: {exc}")
            missing.add(system_file)
            _apply_log(workflow, f"{system_file}: store restore failed: {exc}")
        return
    warnings.extend(_clone_dacl_from_reference(workflow, dst, system_file))
    if source_note:
        warnings.append(source_note)
    restored.add(system_file)
    _apply_log(workflow, f"{system_file}: restored from component store")


def _note_inauthentic_live_font(workflow, system_filename: str, target: Path, warnings) -> None:
    store_file = find_winsxs_font(system_filename)
    if store_file is None:
        return
    store_profile = profile(store_file)
    if store_profile and not is_authentic_font(target, store_profile):
        warnings.append(
            f"{system_filename} is not the genuine Windows font and was already replaced; "
            "it will be saved as the previous font."
        )
        _apply_log(workflow, f"{system_filename}: live font is not genuine; saved as previous font")


def backup_and_override_system_fonts(workflow, fonts_manifest: dict[str, dict], progress=None) -> list[str]:
    warnings = []
    backup_root = workflow.paths.original_fonts_root
    workflow.paths.ensure_runtime_dirs()
    _apply_log(workflow, f"backup_and_override_system_fonts start, {len(fonts_manifest)} fonts")

    for info in fonts_manifest.values():
        system_filename = info.get("system_filename")
        if not system_filename:
            continue
        patched = Path(info.get("active_path", ""))
        target = workflow.active_fonts_root / system_filename
        if not target.exists():
            _apply_log(workflow, f"{system_filename}: target missing, skipping")
            continue
        if not patched.exists():
            _apply_log(workflow, f"{system_filename}: generated file missing at {patched}, skipping")
            continue
        if hash_file(target) == hash_file(patched):
            warnings.extend(restore_file_acl(target, backup_root, system_filename))
            _apply_log(workflow, f"{system_filename}: already overridden, restoring ownership and skipping")
            continue

        backup = backup_root / system_filename
        if not backup.exists():
            try:
                shutil.copy2(target, backup)
            except OSError as exc:
                warnings.append(f"Could not back up original font {system_filename}: {exc}")
                _apply_log(workflow, f"{system_filename}: backup failed: {exc}")
                continue
            _emit_progress(workflow, progress, 85, "Checking the Windows component store...")
            _note_inauthentic_live_font(workflow, system_filename, target, warnings)

        snapshot_file_acl(target, backup_root, system_filename)

        try:
            _grant_owner_write(target)
            atomic_replace(patched, target)
            if hash_file(target) == hash_file(patched):
                warnings.extend(restore_file_acl(target, backup_root, system_filename))
                _apply_log(workflow, f"{system_filename}: replaced atomically, hash ok")
                continue
            _apply_log(workflow, f"{system_filename}: replace reported success but hash mismatch")
            warnings.append(f"Protected font {system_filename} was not overwritten as expected.")
            continue
        except OSError as exc:
            _apply_log(workflow, f"{system_filename}: in-place copy failed ({exc}); trying reboot replace")

        staged = schedule_replace_on_reboot(workflow, patched, target)
        if staged is not None:
            restore_file_acl(staged, backup_root, system_filename)
            warnings.extend(restore_file_acl(target, backup_root, system_filename))
            warnings.append(f"Font {system_filename} is locked and will be replaced after restart.")
            _apply_log(workflow, f"{system_filename}: scheduled for reboot replace")
        else:
            warnings.append(f"Could not apply the font to the protected copy of {system_filename}: {exc}")
            _apply_log(workflow, f"{system_filename}: reboot replace failed too")

    if not warnings:
        _apply_log(workflow, "backup_and_override_system_fonts completed cleanly")
    else:
        _apply_log(workflow, f"backup_and_override_system_fonts completed with {len(warnings)} warning(s)")
    return warnings


def restore_original_fonts(workflow, system_files=None, progress=None) -> tuple[set[str], set[str], list[str], set[str]]:
    system_files = system_files or _default_system_files()
    backup_root = workflow.paths.original_fonts_root
    restored = set()
    missing = set()
    deferred = set()
    warnings = []
    store_emitted = False

    def emit_store_check():
        nonlocal store_emitted
        if not store_emitted:
            store_emitted = True
            _emit_progress(workflow, progress, 24, "Checking the Windows component store...")

    for system_file in system_files:
        dst = workflow.active_fonts_root / system_file
        backup = backup_root / system_file

        if not dst.exists():
            if backup.exists():
                try:
                    _grant_owner_write(dst)
                    atomic_replace(backup, dst)
                    warnings.extend(restore_file_acl(dst, backup_root, system_file, final=True))
                except OSError as exc:
                    staged = schedule_replace_on_reboot(workflow, backup, dst)
                    if staged is not None:
                        deferred.add(system_file)
                        restore_file_acl(staged, backup_root, system_file)
                        warnings.append(f"Font {system_file} is locked and will be restored after restart.")
                    else:
                        warnings.append(f"Could not restore original font {system_file}: {exc}")
                        missing.add(system_file)
                    continue
                restored.add(system_file)
            else:
                missing.add(system_file)
            continue

        if not backup.exists():
            emit_store_check()
            store_file = find_winsxs_font(system_file)
            if store_file is not None:
                _restore_from_store(
                    workflow, system_file, dst, store_file,
                    restored, deferred, missing, warnings, None,
                )
            else:
                missing.add(system_file)
            continue

        emit_store_check()
        store_file = find_winsxs_font(system_file)
        if store_file is not None:
            store_profile = profile(store_file)
            if store_profile and not is_authentic_font(backup, store_profile):
                _restore_from_store(
                    workflow, system_file, dst, store_file,
                    restored, deferred, missing, warnings,
                    f"The saved original for {system_file} was not the genuine Windows font; "
                    "restored from the Windows component store.",
                )
                continue

        try:
            _grant_owner_write(dst)
            atomic_replace(backup, dst)
            warnings.extend(restore_file_acl(dst, backup_root, system_file, final=True))
        except OSError as exc:
            staged = schedule_replace_on_reboot(workflow, backup, dst)
            if staged is not None:
                deferred.add(system_file)
                restore_file_acl(staged, backup_root, system_file)
                warnings.append(f"Font {system_file} is locked and will be restored after restart.")
            else:
                warnings.append(f"Could not restore original font {system_file}: {exc}")
                missing.add(system_file)
            continue
        restored.add(system_file)
    return restored, missing, warnings, deferred


def sweep_stale_temp_dirs(temp_root: Path, keep=None) -> tuple[list[str], int]:
    keep = {str(Path(value).resolve()).lower() for value in (keep or set())}
    warnings = []
    removed = 0
    if not temp_root.exists():
        return warnings, removed

    for child in temp_root.iterdir():
        if not child.is_dir():
            continue
        if not (
            child.name.startswith("fontwizard-build-")
            or child.name.startswith("fontwizard-rollback-")
        ):
            continue
        if str(child.resolve()).lower() in keep:
            continue
        try:
            shutil.rmtree(child)
            removed += 1
        except OSError as exc:
            warnings.append(f"Could not remove stale temporary folder {child.name}: {exc}")
    return warnings, removed
