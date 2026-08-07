import ctypes
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from settings import SUPPORTED_WINDOWS_MAJOR, WINDOWS_10_BUILD, WINDOWS_11_BUILD, default_registry_targets, FONTS_DIR
from app_state import hash_file, validate_state


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def windows_status():
    winver = sys.getwindowsversion()
    is_supported = winver.major == SUPPORTED_WINDOWS_MAJOR and winver.build >= WINDOWS_10_BUILD
    if winver.build >= WINDOWS_11_BUILD:
        label = f"Windows 11 (build {winver.build})"
    elif winver.build >= WINDOWS_10_BUILD:
        label = f"Windows 10 (build {winver.build})"
    else:
        label = f"Windows (build {winver.build})"
    return label, is_supported


def _booted_since(timestamp):
    if not timestamp:
        return False

    try:
        applied_at = datetime.fromisoformat(timestamp)
    except ValueError:
        return False

    if applied_at.tzinfo is None:
        applied_at = applied_at.replace(tzinfo=timezone.utc)

    try:
        kernel32 = ctypes.WinDLL("kernel32")
        kernel32.GetTickCount64.restype = ctypes.c_uint64
        uptime_ms = kernel32.GetTickCount64()
        boot_time = datetime.now(timezone.utc) - timedelta(milliseconds=uptime_ms)
    except Exception:
        return False

    return boot_time > (applied_at + timedelta(seconds=2))


def _targets_match(actual, expected):
    if set(actual) != set(expected):
        return False
    for name, filename in expected.items():
        value = actual.get(name)
        if value == filename:
            continue
        if value is None and not (FONTS_DIR / filename).exists():
            continue
        return False
    return True


def _system_copies_reverted(fonts) -> bool:
    mismatches = 0
    for info in fonts.values():
        system_filename = info.get("system_filename")
        expected = info.get("sha256")
        if not system_filename or not expected:
            continue
        live = FONTS_DIR / system_filename
        try:
            actual = hash_file(live)
        except OSError:
            mismatches += 1
            continue
        if actual != expected:
            mismatches += 1
    return mismatches > 0


def _deferred_copies_still_original(fonts, deferred_filenames) -> bool:
    """True if any font queued for a reboot replace still carries the original content."""
    deferred = {name.lower() for name in deferred_filenames}
    for info in fonts.values():
        system_filename = info.get("system_filename")
        expected = info.get("sha256")
        if not system_filename or system_filename.lower() not in deferred:
            continue
        if not expected:
            continue
        live = FONTS_DIR / system_filename
        try:
            if not live.exists() or hash_file(live) != expected:
                return True
        except OSError:
            return True
    return False


def install_state(registry_targets, default_targets, state, paths=None, pending_deletions=None):
    pending_deletions = pending_deletions or set()

    if state:
        install = state.get("install", {})
        expected = install.get("registry_targets", {})
        fonts = install.get("fonts", {})
        if install.get("status") in ("applied", "pending_reboot", "pending_reboot_apply", "clean"):
            expected_matches = (
                (expected.items() <= registry_targets.items()) if fonts else _targets_match(registry_targets, expected)
            )
            if expected_matches:
                if expected == default_targets and not fonts:
                    if install.get("status") == "pending_reboot":
                        if _booted_since(install.get("restored_at")):
                            return "clean"
                        return "pending_reboot_recovery"
                else:
                    deferred = install.get("deferred_system_fonts") or []
                    if deferred and fonts and _deferred_copies_still_original(fonts, deferred):
                        return "pending_reboot_apply"
                    if fonts and _system_copies_reverted(fonts):
                        return "reverted"
                    return "managed"

    if _targets_match(registry_targets, default_targets) and paths:
        orphans = (
            list(FONTS_DIR.glob("*_fontwizard*"))
            + list(FONTS_DIR.glob("*_mod.ttf"))
        )
        if orphans and any(str(o).lower() in pending_deletions for o in orphans):
            return "pending_reboot_recovery"

    if any(
        filename and ("_fontwizard" in filename.lower() or filename.lower().endswith("_mod.ttf"))
        for filename in registry_targets.values()
    ):
        return "managed"

    return "clean"


def experience_state(is_supported, is_admin, install_state):
    if not is_supported:
        return (
            "unsupported",
            "This PC is not supported",
            "Font Wizard supports Windows 10 (build 10240+) and Windows 11.",
            "Run Font Wizard on a Windows 10 or Windows 11 PC.",
        )
    if not is_admin:
        return (
            "needs_admin",
            "Administrator access required",
            "Font Wizard needs to run as Administrator to change system fonts.",
            "Close Font Wizard and reopen it \u2014 accept the security prompt when asked.",
        )
    if install_state == "pending_reboot_apply":
        return (
            "pending_reboot",
            "Restart Windows to finish this font change",
            "The new fonts have been set up, but some files still need a restart to take effect.",
            "Restart your PC to see the new font, or select another font to apply.",
        )
    if install_state == "pending_reboot_recovery":
        return (
            "pending_reboot",
            "Restart Windows to finish recovery",
            "The original fonts have been set up, but some files still need a restart to take effect.",
            "Restart your PC, then open Font Wizard again if you want to apply a new font.",
        )
    if install_state == "reverted":
        return (
            "reverted",
            "Your font is still in place",
            "Windows refreshed a few related font files at startup, but the font you chose is still active and applied. Nothing needs to be done.",
            "To be safe, re-apply from Font Setup, or restore the original Windows fonts from Recovery.",
        )
    if install_state == "managed":
        return (
            "managed",
            "Fonts are currently managed by Font Wizard",
            "Everything looks healthy. You can switch to another font or restore the original Windows fonts at any time.",
            "Use Font Setup to switch fonts, or restore the defaults from Recovery.",
        )
    return (
        "ready",
        "Ready to choose a font",
        "The system is clean and ready.",
        "Use Font Setup to apply a new font, or Recovery to restore the defaults.",
    )


def build_messages(install_state, is_supported):
    if not is_supported:
        return ["Use Font Wizard on Windows 10 or Windows 11."]

    notes = []
    if install_state == "managed":
        notes.append("The current fonts were installed by Font Wizard.")
    if install_state == "reverted":
        notes.append("Windows refreshed a few related font files at startup; your font is still active.")
    if install_state == "pending_reboot_apply":
        notes.append("Restart Windows to finish applying the font, or select another font.")
    if install_state == "pending_reboot_recovery":
        notes.append("Restart Windows to finish restoring the original fonts.")
    notes.append("Use Recovery if you want to put Windows fonts back without applying a new font.")
    return notes


@dataclass
class PreflightReport:
    is_supported: bool
    is_admin: bool
    managed_state_valid: bool
    install_state: str
    headline: str
    summary: str
    can_apply_changes: bool
    can_restore_defaults: bool
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PreflightService:
    def __init__(self, paths, registry, state_store):
        self.paths = paths
        self.registry = registry
        self.state_store = state_store

    def collect(self):
        from operation_files import _read_pending_rename_sources

        default_targets = default_registry_targets()
        registry_targets = self.registry.read_targets(list(default_targets.keys()))
        state = self.state_store.load()
        state_valid = validate_state(state)
        _, is_supported = windows_status()

        pending_renames = _read_pending_rename_sources()
        install = install_state(
            registry_targets,
            default_targets,
            state if state_valid else None,
            self.paths,
            pending_deletions=pending_renames
        )
        admin = is_admin()

        issues = []
        if not is_supported:
            issues.append("This version of Font Wizard supports Windows 10 (build 10240+) and Windows 11 only.")
        warnings = []

        _, headline, summary, _ = experience_state(
            is_supported=is_supported,
            is_admin=admin,
            install_state=install,
        )
        can_apply_changes = is_supported and admin and install != "pending_reboot_recovery"
        can_restore_defaults = is_supported and admin

        return PreflightReport(
            is_supported=is_supported,
            is_admin=admin,
            managed_state_valid=state_valid,
            install_state=install,
            headline=headline,
            summary=summary,
            can_apply_changes=can_apply_changes,
            can_restore_defaults=can_restore_defaults,
            issues=issues,
            warnings=warnings,
        )
