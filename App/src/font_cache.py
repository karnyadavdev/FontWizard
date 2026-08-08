import ctypes
import os
import subprocess
import time
from pathlib import Path


_HWND_BROADCAST = 0xFFFF
_WM_FONTCHANGE = 0x001D
_SMTO_ABORTIFHUNG = 0x0002


_user32 = ctypes.windll.user32
_SendMessageTimeoutW = _user32.SendMessageTimeoutW
_SendMessageTimeoutW.argtypes = [
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_void_p,
    ctypes.c_void_p,
    ctypes.c_uint,
    ctypes.c_uint,
    ctypes.POINTER(ctypes.c_void_p),
]
_SendMessageTimeoutW.restype = ctypes.c_void_p


def broadcast_font_change():
    result = ctypes.c_void_p()
    return bool(
        _SendMessageTimeoutW(
            ctypes.c_void_p(_HWND_BROADCAST),
            _WM_FONTCHANGE,
            None,
            None,
            _SMTO_ABORTIFHUNG,
            5000,
            ctypes.byref(result),
        )
    )


def _run_sc(command, service, timeout=20):
    try:
        completed = subprocess.run(
            ["sc.exe", command, service],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, str(exc)

    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    if completed.returncode == 0:
        return True, output

    already_ok = (
        command == "stop"
        and any(token in output.lower() for token in ("has not been started", "not been started"))
    ) or (
        command == "start"
        and any(token in output.lower() for token in ("already been started", "already running"))
    )
    return already_ok, output


def _cache_paths() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    paths = [
        windir / "ServiceProfiles" / "LocalService" / "AppData" / "Local" / "FontCache",
        windir / "System32" / "FNTCACHE.DAT",
    ]
    if local_app_data:
        paths.append(Path(local_app_data) / "FontCache")
    return paths


def _remove_cache_path(path, warnings):
    if not path.exists():
        return

    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            warnings.append(f"Could not remove font cache file {path}: {exc}")
        return

    for child in path.glob("*"):
        try:
            if child.is_file():
                child.unlink()
        except OSError as exc:
            warnings.append(f"Could not remove font cache file {child}: {exc}")


def refresh_windows_font_cache():
    warnings = []

    stopped, stop_output = _run_sc("stop", "FontCache")
    if not stopped:
        warnings.append(
            "Windows could not stop the Font Cache service. A restart is still required."
        )
    else:
        time.sleep(1)

    for path in _cache_paths():
        _remove_cache_path(path, warnings)

    started, start_output = _run_sc("start", "FontCache")
    if not started:
        warnings.append("Windows could not restart the Font Cache service.")

    if not broadcast_font_change():
        warnings.append("Windows did not acknowledge the font change broadcast.")

    return warnings
