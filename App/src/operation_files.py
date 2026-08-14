import ctypes
import json
import os
import shutil
import subprocess
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


def take_canonical_font_ownership(font_names: list[str], fonts_dir: Path) -> list[str]:
    """
    Takes ownership and grants FullControl permissions (SYSTEM & Administrators)
    using language-independent Well-Known SIDs:
      - *S-1-5-18: NT AUTHORITY\\SYSTEM
      - *S-1-5-32-544: BUILTIN\\Administrators
    """
    warnings = []
    for name in font_names:
        target = fonts_dir / name
        if not target.exists():
            continue
        try:
            subprocess.run(
                ["takeown", "/F", str(target), "/A"],
                check=False,
                capture_output=True,
                creationflags=0x08000000,
            )
            subprocess.run(
                ["icacls", str(target), "/grant", "*S-1-5-18:F", "*S-1-5-32-544:F", "/c"],
                check=False,
                capture_output=True,
                creationflags=0x08000000,
            )
        except Exception as exc:
            warnings.append(f"Permission grant warning for {name}: {exc}")
    return warnings


def find_original_font_backup(workflow, name: str) -> Path | None:
    """
    Finds authentic original system font file across backup directories,
    workspace scratch locations, and WinSxS servicing store.
    Caches discovered font into %PROGRAMDATA%\\Font Wizard\\backup.
    """
    backup_dir = workflow.paths.backup_root
    cached = backup_dir / name
    if cached.exists() and cached.stat().st_size > 200_000:
        return cached

    candidate_dirs = [
        workflow.paths.project_root / "scratch" / "original_segoe_backup",
        workflow.paths.project_root.parent / "scratch" / "original_segoe_backup",
        Path(__file__).resolve().parent.parent.parent / "scratch" / "original_segoe_backup",
    ]

    for cdir in candidate_dirs:
        candidate = cdir / name
        if candidate.exists() and candidate.stat().st_size > 200_000:
            try:
                workflow.paths.ensure_runtime_dirs()
                shutil.copy2(candidate, cached)
            except OSError:
                pass
            return candidate

    # WinSxS Servicing Store Fallback
    try:
        from winsxs import find_winsxs_font
        sxs_path = find_winsxs_font(name)
        if sxs_path and sxs_path.exists() and sxs_path.stat().st_size > 200_000:
            try:
                workflow.paths.ensure_runtime_dirs()
                shutil.copy2(sxs_path, cached)
            except OSError:
                pass
            return sxs_path
    except Exception:
        pass

    return None


def backup_canonical_fonts(workflow, font_names: list[str]) -> tuple[list[str], int]:
    """
    Safely backs up original system fonts into %PROGRAMDATA%\\Font Wizard\\backup.
    """
    workflow.paths.ensure_runtime_dirs()
    backup_dir = workflow.paths.backup_root
    warnings = []
    backed_up_count = 0

    for name in font_names:
        dest = backup_dir / name
        if dest.exists() and dest.stat().st_size > 200_000:
            backed_up_count += 1
            continue

        src = find_original_font_backup(workflow, name)
        if not src:
            # If active font in C:\Windows\Fonts is original (large size), back it up
            active = workflow.active_fonts_root / name
            if active.exists() and active.stat().st_size > 200_000:
                src = active

        if src and src.exists():
            try:
                shutil.copy2(src, dest)
                backed_up_count += 1
            except OSError as exc:
                warnings.append(f"Could not back up original font {name}: {exc}")
        else:
            warnings.append(f"Original font file not found for backup: {name}")

    return warnings, backed_up_count


def schedule_canonical_replacement(workflow, artifacts: dict[str, dict]) -> tuple[dict, list[str]]:
    """
    Stages custom font files into C:\\Windows\\Fonts\\staged_replace_* and registers
    atomic physical in-place overwrite via MoveFileExW with SYSTEM:F permissions.
    """
    font_names = [a["system_filename"] for a in artifacts.values()]
    perm_warnings = take_canonical_font_ownership(font_names, workflow.active_fonts_root)

    manifest = {}
    warnings = list(perm_warnings)
    scheduled_count = 0

    for artifact in artifacts.values():
        system_filename = artifact["system_filename"]
        target_path = workflow.active_fonts_root / system_filename
        staged_src = workflow.active_fonts_root / f"staged_replace_{system_filename}"

        shutil.copy2(artifact["staged_path"], staged_src)

        try:
            subprocess.run(
                ["icacls", str(staged_src), "/grant", "*S-1-5-18:F", "*S-1-5-32-544:F", "/c"],
                check=False,
                capture_output=True,
                creationflags=0x08000000,
            )
        except Exception:
            pass

        ok = _MoveFileExW(
            str(staged_src),
            str(target_path),
            _MOVEFILE_DELAY_UNTIL_REBOOT | _MOVEFILE_REPLACE_EXISTING,
        )
        if ok:
            scheduled_count += 1
        else:
            warnings.append(f"Failed to schedule boot replacement for {system_filename}")

        manifest[artifact["weight"]] = {
            "source_path": artifact["source_path"],
            "family_name": artifact["family_name"],
            "full_name": artifact["full_name"],
            "system_filename": system_filename,
            "staged_path": str(staged_src),
            "target_path": str(target_path),
            "sha256": artifact["hash"],
        }

    return manifest, warnings


def schedule_canonical_restore(workflow, font_names: list[str]) -> tuple[int, list[str]]:
    take_canonical_font_ownership(font_names, workflow.active_fonts_root)
    warnings = []
    scheduled_count = 0

    for name in font_names:
        backup_file = find_original_font_backup(workflow, name)

        if not backup_file or not backup_file.exists():
            warnings.append(f"Authentic backup file missing for {name}; skipping restore.")
            continue

        target_path = workflow.active_fonts_root / name
        staged_src = workflow.active_fonts_root / f"staged_restore_{name}"

        try:
            shutil.copy2(backup_file, staged_src)
        except Exception as exc:
            warnings.append(f"Could not stage {name} for restore: {exc}")
            continue

        try:
            subprocess.run(
                ["icacls", str(staged_src), "/grant", "*S-1-5-18:F", "*S-1-5-32-544:F", "/c"],
                check=False,
                capture_output=True,
                creationflags=0x08000000,
            )
        except Exception:
            pass

        ok = _MoveFileExW(
            str(staged_src),
            str(target_path),
            _MOVEFILE_DELAY_UNTIL_REBOOT | _MOVEFILE_REPLACE_EXISTING,
        )
        if ok:
            scheduled_count += 1
        else:
            warnings.append(f"Failed to schedule restore for {name}")

    try:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\FontSubstitutes",
            0,
            winreg.KEY_SET_VALUE | winreg.KEY_WOW64_64KEY,
        ) as key:
            for sub_name in ["Segoe WPC", "Segoe WPC Semibold"]:
                try:
                    winreg.DeleteValue(key, sub_name)
                except OSError:
                    pass
    except OSError:
        pass

    return scheduled_count, warnings


def purge_system_font_cache() -> list[str]:
    warnings = []
    subprocess.run(["net", "stop", "FontCache"], check=False, capture_output=True, creationflags=0x08000000)

    fntcache = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32" / "FNTCACHE.DAT"
    if fntcache.exists():
        try:
            fntcache.unlink(missing_ok=True)
        except OSError:
            _MoveFileExW(str(fntcache), None, _MOVEFILE_DELAY_UNTIL_REBOOT)

    dwrite_cache_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "ServiceProfiles" / "LocalService" / "AppData" / "Local" / "FontCache"
    if dwrite_cache_dir.exists():
        for item in dwrite_cache_dir.glob("FontCache-*.dat"):
            try:
                item.unlink(missing_ok=True)
            except OSError:
                _MoveFileExW(str(item), None, _MOVEFILE_DELAY_UNTIL_REBOOT)

    return warnings


def cleanup_orphaned_pending_ops(workflow) -> tuple[list[str], bool]:
    referenced = _read_pending_rename_sources()
    warnings = []
    is_pending = False

    # Check staged files in Fonts root
    for pattern in ("staged_replace_*", "staged_restore_*"):
        for path in workflow.active_fonts_root.glob(pattern):
            if str(path).lower() in referenced:
                is_pending = True
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError as exc:
                warnings.append(f"Could not remove stale staged file {path}: {exc}")

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
