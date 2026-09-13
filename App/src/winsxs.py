import os
import re
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

from font_detection import infer_family_label_from_strings

WINSXS_ROOT = Path(
    os.environ.get(
        "FONTWIZARD_WINSXS_DIR",
        Path(os.environ.get("WINDIR", r"C:\Windows")) / "WinSxS",
    )
)

_SKIP_DIR_NAMES = {"manifests", "backup", "r"}
_SKIP_DIR_PREFIXES = ("x86_", "wow64_", "arm64_")
_SERVICING_RE = re.compile(r"10\.0\.\d+\.(\d+)")

import sys

_GENERIC_TOLERANCE = 0.1


def _is_windows_11() -> bool:
    try:
        winver = sys.getwindowsversion()
        return winver.major == 10 and winver.build >= 22000
    except Exception:
        return True


EXPECTED_FAMILIES = {
    "segoeui.ttf": ("segoe ui", "Microsoft Corporation", (4650, 2100)),
    "segoeuib.ttf": ("segoe ui", "Microsoft Corporation", (4650, 2100)),
    "segoeuii.ttf": ("segoe ui", "Microsoft Corporation", (3050, 2050)),
    "segoeuiz.ttf": ("segoe ui", "Microsoft Corporation", (3050, 2050)),
    "segoeuil.ttf": ("segoe ui", "Microsoft Corporation", (4650, 2100)),
    "segoeuisl.ttf": ("segoe ui", "Microsoft Corporation", (4650, 2100)),
    "seguisb.ttf": ("segoe ui", "Microsoft Corporation", (4650, 2100)),
    "seguibl.ttf": ("segoe ui", "Microsoft Corporation", (2150, 1500)),
    "seguibli.ttf": ("segoe ui", "Microsoft Corporation", (2150, 1500)),
    "seguili.ttf": ("segoe ui", "Microsoft Corporation", (3050, 2050)),
    "seguisbi.ttf": ("segoe ui", "Microsoft Corporation", (3050, 2050)),
    "seguisli.ttf": ("segoe ui", "Microsoft Corporation", (3050, 2050)),
    "seguivar.ttf": ("segoe ui variable", "Microsoft Corporation", (2250, 2250)),
    "consola.ttf": ("consolas", "Microsoft Corporation", 2727),
    "consolab.ttf": ("consolas", "Microsoft Corporation", 2647),
    "consolai.ttf": ("consolas", "Microsoft Corporation", 2735),
    "consolaz.ttf": ("consolas", "Microsoft Corporation", 2655),
    "lucon.ttf": ("lucida console", None, 650),
    "cascadiacode.ttf": ("cascadia code", "Microsoft Corporation", 1500),
    "cascadiamono.ttf": ("cascadia mono", "Microsoft Corporation", 1500),
}

_PROFILE_CACHE = {}
_CACHE = {}


def reset_winsxs_cache() -> None:
    _PROFILE_CACHE.clear()
    _CACHE.clear()


def expected_entry(system_filename: str):
    entry = EXPECTED_FAMILIES.get(Path(system_filename).name.lower())
    if not entry:
        return None
    family, manufacturer, floors = entry
    if isinstance(floors, tuple):
        min_glyphs = floors[0] if _is_windows_11() else floors[1]
    else:
        min_glyphs = floors
    return {
        "family_label": family,
        "manufacturer": manufacturer,
        "min_glyph_count": min_glyphs,
    }


def _glyph_count(font):
    try:
        return font["maxp"].numGlyphs
    except Exception:
        return len(font.getGlyphOrder())


def _profile(path: Path):
    resolved = str(path.resolve())
    cached = _PROFILE_CACHE.get(resolved)
    if cached is not None:
        return cached

    try:
        font = TTFont(path)
    except (TTLibError, OSError, ValueError):
        _PROFILE_CACHE[resolved] = None
        return None
    try:
        family_name = font["name"].getBestFamilyName() or path.stem
        full_name = font["name"].getBestFullName() or path.stem
        try:
            weight_class = font["OS/2"].usWeightClass
        except Exception:
            weight_class = 400
        try:
            is_italic = bool(font["head"].macStyle & 0x2) or font["post"].italicAngle != 0
        except Exception:
            is_italic = False
        glyph_count = _glyph_count(font)
        manufacturer = font["name"].getName(8, 3, 1, 0x409)
        manufacturer = manufacturer.toUnicode() if manufacturer else None
        profile = {
            "family_label": infer_family_label_from_strings(
                family_name, full_name, path.stem
            ),
            "manufacturer": manufacturer.strip() if manufacturer else None,
            "weight_class": weight_class,
            "is_italic": is_italic,
            "glyph_count": glyph_count,
        }
    except Exception:
        _PROFILE_CACHE[resolved] = None
        return None
    finally:
        font.close()
    _PROFILE_CACHE[resolved] = profile
    return profile


def profile(path: Path):
    return _profile(path)


def _normalized(value):
    return (value or "").strip().lower()


def is_authentic_font(path, reference_metadata) -> bool:
    profile = _profile(path)
    if profile is None:
        return False

    expected_family = _normalized(reference_metadata.get("family_label"))
    if expected_family and expected_family != _normalized(profile["family_label"]):
        return False

    expected_manufacturer = _normalized(reference_metadata.get("manufacturer"))
    if (
        expected_manufacturer
        and expected_manufacturer != _normalized(profile["manufacturer"])
    ):
        return False

    if reference_metadata.get("is_italic") is not None and bool(
        reference_metadata["is_italic"]
    ) != bool(profile["is_italic"]):
        return False

    if reference_metadata.get("weight_class") and abs(
        profile["weight_class"] - reference_metadata["weight_class"]
    ) > 100:
        return False

    if reference_metadata.get("glyph_count") and abs(
        profile["glyph_count"] - reference_metadata["glyph_count"]
    ) > _GENERIC_TOLERANCE * reference_metadata["glyph_count"]:
        return False

    if reference_metadata.get("min_glyph_count") and profile[
        "glyph_count"
    ] < reference_metadata["min_glyph_count"]:
        return False

    return True


def _skip_dir(name: str) -> bool:
    lower = name.lower()
    if lower in _SKIP_DIR_NAMES:
        return True
    return lower.startswith(_SKIP_DIR_PREFIXES)


def _servicing_build(package_dir_name: str) -> int:
    match = _SERVICING_RE.search(package_dir_name)
    if not match:
        return 0
    return int(match.group(1))


def _scan_winsxs(target_names) -> None:
    wanted = {name.lower() for name in target_names}
    found = {name: [] for name in wanted}

    if not WINSXS_ROOT.is_dir():
        for name in wanted:
            _CACHE[name] = None
        return

    for root, dirs, files in os.walk(WINSXS_ROOT, topdown=True):
        dirs[:] = [entry for entry in dirs if not _skip_dir(entry)]
        for filename in files:
            lower = filename.lower()
            if lower not in wanted:
                continue
            path = Path(root) / filename
            profile = _profile(path)
            if profile is None:
                continue
            entry = EXPECTED_FAMILIES.get(lower)
            if entry and not is_authentic_font(path, expected_entry(lower)):
                continue
            try:
                size = path.stat().st_size
            except OSError:
                size = 0
            found[lower].append(
                (_servicing_build(os.path.basename(root)), size, path)
            )

    for lower, candidates in found.items():
        if not candidates:
            _CACHE[lower] = None
            continue
        best = max(candidates, key=lambda candidate: (candidate[0], candidate[1]))
        _CACHE[lower] = best[2]


def find_winsxs_font(system_filename) -> Path | None:
    name = Path(system_filename).name
    lower = name.lower()
    if lower not in _CACHE:
        _scan_winsxs(set(EXPECTED_FAMILIES) | {lower})
    return _CACHE.get(lower)
