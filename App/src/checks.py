import ctypes
import hashlib
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

from settings import (
    APP_NAME,
    SUPPORTED_WINDOWS_MAJOR,
    WINDOWS_10_MIN_BUILD,
    WINDOWS_11_BUILD,
    default_registry_targets,
    FONTS_DIR,
    PREFLIGHT_MIN_DISK_CORE_MB,
    PREFLIGHT_MIN_DISK_CJK_MB,
    PREFLIGHT_MIN_DISK_RESTORE_MB,
)
from app_state import validate_state


def is_admin():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def windows_status():
    winver = sys.getwindowsversion()
    is_win11 = winver.major == SUPPORTED_WINDOWS_MAJOR and winver.build >= WINDOWS_11_BUILD
    is_win10 = winver.major == SUPPORTED_WINDOWS_MAJOR and winver.build >= WINDOWS_10_MIN_BUILD
    is_supported = is_win11 or is_win10
    if is_win11:
        label = f"Windows 11 (build {winver.build})"
    elif is_win10:
        label = f"Windows 10 (build {winver.build})"
    else:
        label = f"Windows build {winver.build}"
    return label, is_supported


def _has_pending_font_operations(pending_deletions):
    if not pending_deletions:
        return False
    for item in pending_deletions:
        lower = str(item).lower()
        if (
            "staged_replace_" in lower
            or "staged_restore_" in lower
            or "_fontwizard" in lower
            or "_pending_replace" in lower
        ):
            return True
    return False


def _is_physically_custom(paths=None):
    active_segoe = FONTS_DIR / "segoeui.ttf"
    if not active_segoe.exists():
        return False

    backup_root = getattr(paths, "backup_root", None) if paths else None
    backup_root = Path(backup_root) if backup_root else None

    candidate_fonts = (
        "segoeui.ttf", "segoeuib.ttf", "segoeuii.ttf", "segoeuiz.ttf",
        "segoeuil.ttf", "segoeuisl.ttf", "seguisb.ttf", "SegUIVar.ttf",
        "consola.ttf", "consolab.ttf", "consolai.ttf", "consolaz.ttf",
        "lucon.ttf", "tahoma.ttf", "tahomabd.ttf", "micross.ttf",
        "CascadiaCode.ttf", "CascadiaMono.ttf",
    )

    try:
        from winsxs import expected_entry, is_authentic_font
    except ImportError:
        expected_entry, is_authentic_font = None, None

    for name in candidate_fonts:
        active = FONTS_DIR / name
        if not active.is_file():
            continue

        # 1. Compare against local backup if available
        if backup_root is not None:
            backup = backup_root / name
            if backup.is_file():
                try:
                    if _sha256_file(active) != _sha256_file(backup):
                        return True
                    # This font matches its backup; keep checking remaining fonts
                    continue
                except OSError:
                    pass

        # 2. If no backup exists or hash comparison was skipped, check authenticity
        if expected_entry and is_authentic_font:
            try:
                entry = expected_entry(name)
                if entry and not is_authentic_font(active, entry):
                    return True
            except Exception:
                pass

    return False


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_entries(install):
    """Verifiable (filename, sha256) pairs from a stored install manifest."""
    fonts = (install or {}).get("fonts") or {}
    entries = []
    if isinstance(fonts, dict):
        for entry in fonts.values():
            if not isinstance(entry, dict):
                continue
            name = entry.get("system_filename")
            digest = entry.get("sha256")
            if name and digest:
                entries.append((str(name), str(digest)))
    return entries


def _classify_live(entries, paths):
    """Tag each recorded font as custom / stock / other / missing."""
    backup_root = getattr(paths, "backup_root", None) if paths else None
    backup_root = Path(backup_root) if backup_root else None
    states = []
    for name, digest in entries:
        try:
            live = FONTS_DIR / name
            if not live.is_file():
                states.append("missing")
                continue
            live_hash = _sha256_file(live)
            if live_hash == digest:
                states.append("custom")
                continue
            if backup_root is not None:
                backup = backup_root / name
                if backup.is_file() and live_hash == _sha256_file(backup):
                    states.append("stock")
                    continue
            states.append("other")
        except OSError:
            states.append("other")
    return states


def _verify_managed_install(install, paths):
    """Decide the real state when our records claim the fonts are ours.

    Returns "managed" if the live files match the manifest, "clean" if
    they match our stock backups (something — e.g. a Windows Update —
    restored the originals), "partial" when only some were touched, or
    None when there is nothing verifiable or the files are neither
    (unknown customization: keep prior behavior).
    """
    entries = _manifest_entries(install)
    if not entries:
        return None
    try:
        states = _classify_live(entries, paths)
    except Exception:
        return None
    if not states:
        return None
    if all(s == "custom" for s in states):
        return "managed"
    if all(s == "stock" for s in states):
        return "clean"
    if any(s in ("custom", "stock") for s in states):
        return "partial"
    return None


def install_state(registry_targets, default_targets, state, paths=None, pending_deletions=None):
    pending_deletions = pending_deletions or set()
    has_pending = _has_pending_font_operations(pending_deletions)


    if state:
        install = state.get("install", {})
        status = install.get("status")

        if status == "clean":
            if has_pending:
                return "pending_reboot_recovery"
            verified = _verify_managed_install(install, paths)
            if verified is not None:
                return verified
            if _is_physically_custom(paths=paths):
                return "managed"
            return "clean"

        if status == "pending_reboot_apply":
            if has_pending:
                return "pending_reboot_apply"
            verified = _verify_managed_install(install, paths)
            return verified if verified is not None else "managed"

        if status == "pending_reboot_recovery":
            if has_pending:
                return "pending_reboot_recovery"
            verified = _verify_managed_install(install, paths)
            if verified is not None:
                return verified
            if _is_physically_custom(paths=paths):
                return "managed"
            return "clean"

        if status in ("managed", "applied"):
            if has_pending:
                return "pending_reboot_apply"
            # Never trust the record alone: a Windows Update may have
            # replaced our files since. Verify bytes before claiming managed.
            verified = _verify_managed_install(install, paths)
            return verified if verified is not None else "managed"

        if status == "partial":
            if has_pending:
                for item in pending_deletions:
                    if "staged_restore_" in str(item).lower():
                        return "pending_reboot_recovery"
                return "pending_reboot_apply"
            verified = _verify_managed_install(install, paths)
            if verified is not None:
                return verified
            return "partial"

    if has_pending:
        for item in pending_deletions:
            if "staged_restore_" in str(item).lower():
                return "pending_reboot_recovery"
        return "pending_reboot_apply"

    if _is_physically_custom(paths=paths):
        return "managed"

    return "clean"



def experience_state(is_supported, is_admin, install_state, issues=None):
    if not is_supported:
        return (
            "unsupported",
            "This Windows is not supported",
            "Font Wizard supports Windows 10 (build 10240+) and Windows 11.",
            "Run Font Wizard on a supported Windows 10 or Windows 11 PC.",
        )
    if not is_admin:
        return (
            "needs_admin",
            "Administrator access required",
            "Font Wizard needs to run as Administrator to change system fonts.",
            "Close Font Wizard and reopen it \u2014 accept the security prompt when asked.",
        )
    if issues:
        first_issue = issues[0]
        if "disk space" in first_issue.lower():
            import re
            m = re.search(r"At least ([\d\.]+\s*(?:MB|GB))", first_issue)
            req = m.group(1) if m else "space"
            drive_m = re.search(r"on\s+([A-Za-z]:)", first_issue)
            drive = drive_m.group(1) if drive_m else "C:"
            headline = f"Free up at least {req} on {drive} to continue"
            return (
                "low_disk_space",
                headline,
                first_issue,
                f"Free up at least {req} on {drive}, then try again.",
            )
        clean_first = first_issue.split(".")[0].strip()
        headline = clean_first if len(clean_first) <= 60 else "System issue detected — resolve before continuing"
        return (
            "issue",
            headline,
            first_issue,
            "Resolve the issue before applying font changes.",
        )
    if install_state == "pending_reboot_apply":
        return (
            "pending_reboot",
            "Restart Windows to finish this fonts change",
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
    if install_state == "partial":
        return (
            "partial",
            "Windows update restored some fonts, you need to apply again",
            "A Windows update or another app put some original Windows fonts back. Apply your font again to finish, or restore all the original fonts.",
            "Select your font and choose Apply Changes to finish, or restore the original Windows fonts.",
        )
    if install_state == "managed":
        return (
            "managed",
            "New fonts are active, change or restore anytime",
            "Everything looks healthy. You can switch to another font or restore the original Windows fonts at any time.",
            "Use Font Setup to switch fonts, or restore the defaults from Recovery.",
        )
    return (
        "ready",
            "Ready to give your system a fresh look",
        "The system is clean and ready.",
        "Use Font Setup to apply a new font, or Recovery to restore the defaults.",
    )


def build_messages(install_state, is_supported):
    if not is_supported:
        return ["Use Font Wizard on Windows 10 or Windows 11."]

    notes = []
    if install_state == "managed":
        notes.append("The current fonts were installed by Font Wizard.")
    if install_state == "partial":
        notes.append("Some original Windows fonts were restored since the font was last applied.")
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


def _has_regional_fonts_installed(state_store) -> bool:
    """Safely inspects state store to see if any regional fonts are recorded.
    If the state file is unreadable or malformed, falls back to True (conservative 400 MB requirement).
    """
    if not state_store:
        return False
    try:
        data = state_store.load_or_empty()
        if not isinstance(data, dict):
            return True
        install = data.get("install")
        if install is None:
            return False
        if not isinstance(install, dict):
            return True
        fonts = install.get("fonts")
        if fonts is None:
            return False
        if not isinstance(fonts, dict):
            return True
        return any(isinstance(k, str) and k.startswith("regional_") for k in fonts)
    except Exception:
        return True


class PreflightService:
    def __init__(self, paths, registry, state_store):
        self.paths = paths
        self.registry = registry
        self.state_store = state_store

    def collect(self, *, include_regional: bool = True, is_restore: bool = False):
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
            issues.append("This version of Font Wizard supports Windows 10 (build 10240+) and Windows 11.")

        # Disk Space Preflight: Dynamic threshold (180 MB core, 180/400 MB restore, 1.2 GB CJK compilation)
        has_restore_space = True
        try:
            target_drive = Path(FONTS_DIR).anchor or "C:\\"
            free_bytes = shutil.disk_usage(target_drive).free
            has_reg = _has_regional_fonts_installed(self.state_store)

            restore_min_mb = PREFLIGHT_MIN_DISK_RESTORE_MB if has_reg else PREFLIGHT_MIN_DISK_CORE_MB
            has_restore_space = free_bytes >= int(restore_min_mb * 1024 * 1024)

            if is_restore:
                min_mb = restore_min_mb
            else:
                if include_regional:
                    min_mb = PREFLIGHT_MIN_DISK_CJK_MB
                elif has_reg:
                    min_mb = PREFLIGHT_MIN_DISK_RESTORE_MB
                else:
                    min_mb = PREFLIGHT_MIN_DISK_CORE_MB

            min_required = int(min_mb * 1024 * 1024)
            if free_bytes < min_required:
                free_mb = free_bytes // (1024 * 1024)
                req_str = f"{min_mb} MB" if is_restore or not include_regional else "1.2 GB"
                issues.append(
                    f"Insufficient free disk space on {target_drive} ({free_mb} MB available). "
                    f"At least {req_str} free space is required to safely stage font backups and replacements."
                )
        except Exception:
            pass

        warnings = []


        readiness, headline, summary, next_step = experience_state(
            is_supported=is_supported,
            is_admin=admin,
            install_state=install,
            issues=issues,
        )
        non_disk_issues = [issue for issue in issues if "disk space" not in issue.lower()]
        can_apply_changes = is_supported and admin and install != "pending_reboot_recovery" and not issues
        can_restore_defaults = (
            is_supported
            and admin
            and install != "pending_reboot_recovery"
            and not non_disk_issues
            and has_restore_space
        )
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


def check_disk_space_only(*, include_regional: bool = True, is_restore: bool = False, has_regional_installed: bool = False) -> tuple[bool, str | None]:
    if is_restore:
        min_mb = PREFLIGHT_MIN_DISK_RESTORE_MB if has_regional_installed else PREFLIGHT_MIN_DISK_CORE_MB
    else:
        if include_regional:
            min_mb = PREFLIGHT_MIN_DISK_CJK_MB
        elif has_regional_installed:
            min_mb = PREFLIGHT_MIN_DISK_RESTORE_MB
        else:
            min_mb = PREFLIGHT_MIN_DISK_CORE_MB
    try:
        target_drive = Path(FONTS_DIR).anchor or "C:\\"
        usage = shutil.disk_usage(target_drive)
        free_mb = usage.free // (1024 * 1024)
        if free_mb < min_mb:
            req_str = "1.2 GB" if (include_regional and not is_restore) else f"{min_mb} MB"
            return False, f"Low disk space: {free_mb} MB available on {target_drive}, requires {req_str}."
        return True, None
    except Exception:
        return True, None
