import ctypes
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta

from settings import APP_NAME, SUPPORTED_WINDOWS_MAJOR, WINDOWS_11_BUILD, default_registry_targets, FONTS_DIR
from app_state import validate_state


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def windows_status():
    winver = sys.getwindowsversion()
    is_supported = winver.major == SUPPORTED_WINDOWS_MAJOR and winver.build >= WINDOWS_11_BUILD
    label = f"Windows 11 (build {winver.build})" if is_supported else f"Windows build {winver.build}"
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


def install_state(registry_targets, default_targets, state, paths=None, pending_deletions=None):
    pending_deletions = pending_deletions or set()

    if state:
        install = state.get("install", {})
        expected = install.get("registry_targets", {})
        fonts = install.get("fonts", {})
        if install.get("status") in ("applied", "pending_reboot", "clean") and expected == registry_targets:
            if expected == default_targets and not fonts:
                if install.get("status") == "pending_reboot":
                    if _booted_since(install.get("restored_at")):
                        return "clean"
                    return "pending_reboot_recovery"
            else:
                if not _booted_since(install.get("applied_at")):
                    return "pending_reboot_apply"
                return "managed"

    if registry_targets == default_targets and paths:
        orphans = (
            list(FONTS_DIR.glob("*_fontwizard*"))
            + list(FONTS_DIR.glob("*_mod.ttf"))
        )
        if orphans and all(str(o).lower() in pending_deletions for o in orphans):
            return "pending_reboot_recovery"

    return "clean"


def experience_state(is_supported, is_admin, install_state):
    if not is_supported:
        return (
            "unsupported",
            "This PC is not supported",
            "Font Wizard only supports Windows 11.",
            "Run Font Wizard on a Windows 11 PC.",
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
        return ["Use Font Wizard on Windows 11."]

    notes = []
    if install_state == "managed":
        notes.append("The current fonts were installed by Font Wizard.")
    if install_state == "pending_reboot_apply":
        notes.append("Restart Windows to fully apply the font, or select another font to apply.")
    if install_state == "pending_reboot_recovery":
        notes.append("Restart Windows before applying another font.")
    notes.append("Use Recovery if you want to put Windows fonts back without applying a new font.")
    return notes


@dataclass
class PreflightReport:
    app_name: str
    windows_label: str
    is_supported: bool
    is_admin: bool
    registry_targets: dict[str, str | None]
    default_targets: dict[str, str]
    managed_state_present: bool
    managed_state_valid: bool
    install_state: str
    readiness: str
    headline: str
    summary: str
    next_step: str
    can_apply_changes: bool
    can_restore_defaults: bool
    messages: list[str] = field(default_factory=list)
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
        windows_label, is_supported = windows_status()

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
            issues.append("This version of Font Wizard supports Windows 11 only.")
        warnings = []

        readiness, headline, summary, next_step = experience_state(
            is_supported=is_supported,
            is_admin=admin,
            install_state=install,
        )
        can_apply_changes = is_supported and admin and install != "pending_reboot_recovery"
        can_restore_defaults = is_supported and admin
        messages = build_messages(
            install_state=install,
            is_supported=is_supported,
        )

        return PreflightReport(
            app_name=APP_NAME,
            windows_label=windows_label,
            is_supported=is_supported,
            is_admin=admin,
            registry_targets=registry_targets,
            default_targets=default_targets,
            managed_state_present=state is not None,
            managed_state_valid=state_valid,
            install_state=install,
            readiness=readiness,
            headline=headline,
            summary=summary,
            next_step=next_step,
            can_apply_changes=can_apply_changes,
            can_restore_defaults=can_restore_defaults,
            messages=messages,
            issues=issues,
            warnings=warnings,
        )
