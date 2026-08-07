import ctypes
import os
import subprocess
import time
from ctypes import wintypes
from pathlib import Path


_HWND_BROADCAST = 0xFFFF
_WM_FONTCHANGE = 0x001D
_SMTO_ABORTIFHUNG = 0x0002

_SC_MANAGER_CONNECT = 0x0001
_SERVICE_QUERY_STATUS = 0x0004
_SERVICE_STOPPED = 0x0001
_SERVICE_RUNNING = 0x0004


class _SERVICE_STATUS(ctypes.Structure):
    _fields_ = [
        ("dwServiceType", wintypes.DWORD),
        ("dwCurrentState", wintypes.DWORD),
        ("dwControlsAccepted", wintypes.DWORD),
        ("dwWin32ExitCode", wintypes.DWORD),
        ("dwServiceSpecificExitCode", wintypes.DWORD),
        ("dwCheckPoint", wintypes.DWORD),
        ("dwWaitHint", wintypes.DWORD),
    ]


_advapi32 = ctypes.windll.advapi32
_advapi32.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
_advapi32.OpenSCManagerW.restype = wintypes.HANDLE
_advapi32.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
_advapi32.OpenServiceW.restype = wintypes.HANDLE
_advapi32.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(_SERVICE_STATUS)]
_advapi32.QueryServiceStatus.restype = wintypes.BOOL
_advapi32.CloseServiceHandle.argtypes = [wintypes.HANDLE]
_advapi32.CloseServiceHandle.restype = wintypes.BOOL


def _query_service_state(service: str):
    service_manager = _advapi32.OpenSCManagerW(None, None, _SC_MANAGER_CONNECT)
    if not service_manager:
        return None
    try:
        service_handle = _advapi32.OpenServiceW(service_manager, service, _SERVICE_QUERY_STATUS)
        if not service_handle:
            return None
        try:
            status = _SERVICE_STATUS()
            if not _advapi32.QueryServiceStatus(service_handle, ctypes.byref(status)):
                return None
            return status.dwCurrentState
        finally:
            _advapi32.CloseServiceHandle(service_handle)
    finally:
        _advapi32.CloseServiceHandle(service_manager)


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

    state = _query_service_state(service)
    harmless = (
        (command == "stop" and (state == _SERVICE_STOPPED or state is None))
        or (command == "start" and state == _SERVICE_RUNNING)
    )
    if harmless:
        return True, output
    return False, output


def _cache_paths() -> list[Path]:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    local_app_data = os.environ.get("LOCALAPPDATA")
    paths = [
        windir / "ServiceProfiles" / "LocalService" / "AppData" / "Local" / "FontCache",
        windir / "System32" / "FNTCACHE.DAT",
    ]
    if local_app_data:
        local_app = Path(local_app_data)
        paths.append(local_app / "FontCache")
        paths.append(local_app / "Microsoft" / "FontCache3.0.0.0.dat")
        packages = local_app / "Packages"
        if packages.exists():
            for child in packages.iterdir():
                if child.is_dir():
                    paths.append(child / "LocalCache" / "Local" / "FontCache")
    return paths


def _grant_access_and_remove(path: Path) -> bool:
    flags = subprocess.CREATE_NO_WINDOW
    snapshot = None
    if os.environ.get("TEMP"):
        snapshot = Path(os.environ["TEMP"]) / f"fontwizard-acl-{os.getpid()}.sda"
        try:
            completed = subprocess.run(
                ["icacls.exe", str(path), "/save", str(snapshot)],
                capture_output=True,
                timeout=30,
                creationflags=flags,
            )
            if completed.returncode != 0:
                snapshot.unlink(missing_ok=True)
                snapshot = None
        except (OSError, subprocess.SubprocessError):
            snapshot = None

    removed = False
    granted = False
    try:
        if snapshot is not None:
            subprocess.run(
                ["takeown.exe", "/f", str(path), "/a"],
                capture_output=True,
                timeout=30,
                creationflags=flags,
            )
            subprocess.run(
                ["icacls.exe", str(path), "/grant", "*S-1-5-32-544:F"],
                capture_output=True,
                timeout=30,
                creationflags=flags,
            )
            granted = True
        path.unlink(missing_ok=True)
        removed = not path.exists()
    except (OSError, subprocess.SubprocessError):
        pass
    finally:
        if granted and not removed and snapshot is not None:
            try:
                subprocess.run(
                    ["icacls.exe", str(path), "/restore", str(snapshot)],
                    capture_output=True,
                    timeout=30,
                    creationflags=flags,
                )
            except (OSError, subprocess.SubprocessError):
                pass
        if snapshot is not None:
            try:
                snapshot.unlink(missing_ok=True)
            except OSError:
                pass
    return removed


def _apply_cache_note(warnings):
    note = (
        "Some font cache files could not be cleared, but the font is still applied. "
        "They will refresh on their own after the next restart."
    )
    if note not in warnings:
        warnings.append(note)


def _remove_cache_path(path, warnings):
    if not path.exists():
        return

    if path.is_file():
        try:
            path.unlink()
        except OSError as exc:
            if not _grant_access_and_remove(path):
                _apply_cache_note(warnings)
        return

    for child in path.glob("*"):
        try:
            if child.is_file():
                child.unlink()
        except OSError as exc:
            if not _grant_access_and_remove(child):
                _apply_cache_note(warnings)


def refresh_windows_font_cache():
    warnings = []

    stopped, stop_output = _run_sc("stop", "FontCache")
    _run_sc("stop", "FontCache3.0.0.0")
    if not stopped:
        warnings.append(
            "A Windows service was busy, so the font will fully apply after the next restart. "
            "No action is needed."
        )
    else:
        time.sleep(1)

    for path in _cache_paths():
        _remove_cache_path(path, warnings)

    _run_sc("start", "FontCache3.0.0.0")
    started, start_output = _run_sc("start", "FontCache")
    if not started:
        warnings.append("A Windows service could not be restarted, but your font is still applied. No action is needed.")

    if not broadcast_font_change():
        warnings.append("Some open apps may keep showing the old font until you restart them.")

    return warnings
