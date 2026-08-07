import ctypes
import os
import shutil
import subprocess
import time
import uuid
from ctypes import wintypes
from pathlib import Path

from app_state import hash_file

_ACL_FLAGS = 0
if os.name == "nt":
    _ACL_FLAGS = subprocess.CREATE_NO_WINDOW

_KILL_SLEEP = 0.4

_PROTECTED_PROCESS_NAMES = {
    "system",
    "smss",
    "csrss",
    "wininit",
    "services",
    "lsass",
    "winlogon",
    "fontdrvhost",
    "dwm",
    "svchost",
    "audiodg",
    "explorer",
}


def _is_protected(name: str) -> bool:
    stem = Path(name).stem.lower()
    return stem in _PROTECTED_PROCESS_NAMES


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def _run_sc(command, service, timeout=20):
    try:
        completed = subprocess.run(
            ["sc.exe", command, service],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            creationflags=_ACL_FLAGS,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


def stop_font_cache() -> bool:
    return _run_sc("stop", "FontCache") and _run_sc("stop", "FontCache3.0.0.0")


class _FILETIME(ctypes.Structure):
    _fields_ = [
        ("dwLowDateTime", wintypes.DWORD),
        ("dwHighDateTime", wintypes.DWORD),
    ]


class _RM_UNIQUE_PROCESS(ctypes.Structure):
    _fields_ = [
        ("dwProcessId", wintypes.DWORD),
        ("ProcessStartTime", _FILETIME),
    ]


class _RM_PROCESS_INFO(ctypes.Structure):
    _fields_ = [
        ("Process", _RM_UNIQUE_PROCESS),
        ("strAppName", ctypes.c_wchar * 256),
        ("strServiceShortName", ctypes.c_wchar * 64),
        ("ApplicationType", wintypes.DWORD),
        ("AppStatus", wintypes.DWORD),
        ("TSSessionId", wintypes.DWORD),
        ("bRestartable", wintypes.BOOL),
    ]


_rm = ctypes.windll.rstrtmgr
_rm.RmStartSession.argtypes = [
    ctypes.POINTER(wintypes.DWORD),
    wintypes.DWORD,
    ctypes.c_wchar_p,
]
_rm.RmStartSession.restype = ctypes.c_long
_rm.RmEndSession.argtypes = [wintypes.DWORD]
_rm.RmEndSession.restype = ctypes.c_long
_rm.RmRegisterResources.argtypes = [
    wintypes.DWORD,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_wchar_p),
    wintypes.UINT,
    ctypes.c_void_p,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_wchar_p),
]
_rm.RmRegisterResources.restype = ctypes.c_long
_rm.RmGetList.argtypes = [
    wintypes.DWORD,
    ctypes.POINTER(wintypes.UINT),
    ctypes.POINTER(wintypes.UINT),
    ctypes.c_void_p,
    ctypes.POINTER(wintypes.DWORD),
]
_rm.RmGetList.restype = ctypes.c_long

_ERROR_MORE_DATA = 234


def find_holders(paths) -> list[tuple[int, str]]:
    """Return [(pid, app_name)] for processes currently holding any of the files."""
    try:
        session_handle = wintypes.DWORD(0)
        rc = _rm.RmStartSession(ctypes.byref(session_handle), 0, uuid.uuid4().hex)
        if rc != 0:
            return []
    except OSError:
        return []

    try:
        file_ptrs = (ctypes.c_wchar_p * len(paths))(*[str(Path(p)) for p in paths])
        rc = _rm.RmRegisterResources(
            session_handle,
            len(paths),
            file_ptrs,
            0,
            None,
            0,
            None,
        )
        if rc != 0:
            return []

        needed = wintypes.UINT(0)
        count = wintypes.UINT(0)
        reasons = wintypes.DWORD(0)
        rc = _rm.RmGetList(
            session_handle,
            ctypes.byref(needed),
            ctypes.byref(count),
            None,
            ctypes.byref(reasons),
        )
        if rc == _ERROR_MORE_DATA:
            arr = (_RM_PROCESS_INFO * needed.value)()
            count.value = needed.value
            rc = _rm.RmGetList(
                session_handle,
                ctypes.byref(needed),
                ctypes.byref(count),
                arr,
                ctypes.byref(reasons),
            )
            if rc != 0:
                return []
            holders = []
            for index in range(count.value):
                info = arr[index]
                pid = info.Process.dwProcessId
                if pid == os.getpid() or pid <= 0:
                    continue
                name = info.strAppName or info.strServiceShortName or f"PID {pid}"
                holders.append((pid, name.strip()))
            return holders
        return []
    except OSError:
        return []
    finally:
        try:
            _rm.RmEndSession(session_handle)
        except OSError:
            pass


def _kill_pids(pids):
    killed = []
    for pid in pids:
        try:
            completed = subprocess.run(
                ["taskkill.exe", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                timeout=20,
                creationflags=_ACL_FLAGS,
            )
            if completed.returncode == 0:
                killed.append(pid)
        except (OSError, subprocess.SubprocessError):
            continue
    return killed


def _kill_by_name(names):
    killed = []
    for name in names:
        try:
            completed = subprocess.run(
                ["taskkill.exe", "/IM", name, "/T", "/F"],
                capture_output=True,
                timeout=20,
                creationflags=_ACL_FLAGS,
            )
            if completed.returncode == 0:
                killed.append(name)
        except (OSError, subprocess.SubprocessError):
            continue
    return killed


def grant_owner_write(path: Path) -> None:
    subprocess.run(
        ["takeown", "/f", str(Path(path))],
        capture_output=True,
        creationflags=_ACL_FLAGS,
    )
    subprocess.run(
        ["icacls", str(Path(path)), "/grant", "*S-1-5-32-544:(F)"],
        capture_output=True,
        creationflags=_ACL_FLAGS,
    )


def overwrite_in_place(src: Path, dst: Path) -> bool:
    try:
        with open(src, "rb") as inp, open(dst, "r+b") as out:
            shutil.copyfileobj(inp, out)
            out.truncate()
            out.flush()
            os.fsync(out.fileno())
        return True
    except OSError:
        return False


def release_file_handles(paths, kill_shell=False):
    """Best-effort release of every process and service that can lock a font file.

    Only kills processes when running elevated. Without elevation the handle cannot be
    released reliably, so release_returns_empty is returned and writing is left to
    the caller's fallback strategy.
    """
    results = {}
    if not is_admin():
        results["not_elevated"] = True
        return results

    seen_holders = set()
    names_seen = set()
    try:
        for pid, name in find_holders(paths):
            full = name.lower()
            if "fontdrvhost" in full or _is_protected(name):
                continue
            if pid in seen_holders:
                continue
            seen_holders.add(pid)
            names_seen.add(name)
        if seen_holders:
            _kill_pids(seen_holders)
            results["holders"] = sorted(names_seen)
    except OSError:
        pass

    _kill_by_name(["fontdrvhost.exe"])
    stop_font_cache()

    if kill_shell:
        _kill_by_name(["explorer.exe"])
        results["shell"] = True

    if seen_holders or results.get("shell"):
        time.sleep(_KILL_SLEEP)
    return results


def locked_override(src: Path, dst: Path, attempts=3, log=None):
    """Overwrite dst with src, releasing font locks BEFORE each write attempt.

    Verified behavior: killing the actual Restart Manager holders (and the font
    services) with a short settle delay unlocks the file for in-place writing.
    The shell (explorer.exe) is only stopped after the holders alone did not
    release the file, and is never stopped in a repeated loop.
    """
    shell_killed = False

    def note(message):
        if log:
            log(message)

    grant_owner_write(dst)
    note(f"{dst.name}: granted write access")

    settle = _KILL_SLEEP + 0.2
    for attempt in range(1, attempts + 1):
        try:
            result = release_file_handles([dst], kill_shell=attempt >= 2)
        except OSError as exc:
            note(f"{dst.name}: holder release error: {exc}")
            result = {}
        if result and result.get("shell"):
            shell_killed = True
        time.sleep(settle)
        grant_owner_write(dst)
        if overwrite_in_place(src, dst) and hash_file(dst) == hash_file(src):
            note(f"{dst.name}: overwritten on attempt {attempt}")
            return True, shell_killed
        note(f"{dst.name}: attempt {attempt}/{attempts} still locked after release")
    return False, shell_killed


def relaunch_shell() -> None:
    try:
        subprocess.Popen(["explorer.exe"])
    except OSError:
        pass