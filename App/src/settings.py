import os
from pathlib import Path
import uuid
import hashlib

APP_NAME = "Font Wizard"
APP_GITHUB_URL = "https://github.com/karnyadavdev/fontwizard"
SCHEMA_VERSION = 1

SUPPORTED_WINDOWS_MAJOR = 10
WINDOWS_10_MIN_BUILD = 10240
WINDOWS_11_BUILD = 22000

FONT_EXTENSIONS = {".ttf"}
MANAGED_FONT_SUFFIX = "_fontwizard"

FONT_REGISTRY_SUBKEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

STATIC_WEIGHTS = {
    "regular": "segoeui.ttf",
    "bold": "segoeuib.ttf",
    "italic": "segoeuii.ttf",
    "bold_italic": "segoeuiz.ttf",
    "light": "segoeuil.ttf",
    "semilight": "segoeuisl.ttf",
    "semibold": "seguisb.ttf",
    "black": "seguibl.ttf",
    "black_italic": "seguibli.ttf",
    "light_italic": "seguili.ttf",
    "semibold_italic": "seguisbi.ttf",
    "semilight_italic": "seguisli.ttf",
}

VARIABLE_WEIGHTS = {
    "variable": "SegUIVar.ttf",
}

CONSOLAS_WEIGHTS = {
    "consolas_regular": "consola.ttf",
    "consolas_bold": "consolab.ttf",
    "consolas_italic": "consolai.ttf",
    "consolas_bold_italic": "consolaz.ttf",
}

def get_system_weights(fonts_dir=None):
    target_dir = Path(fonts_dir or FONTS_DIR)
    weights = dict(STATIC_WEIGHTS)
    if (target_dir / "SegUIVar.ttf").exists():
        weights.update(VARIABLE_WEIGHTS)
    for k, v in CONSOLAS_WEIGHTS.items():
        if (target_dir / v).exists():
            weights[k] = v
    return weights

WEIGHTS = get_system_weights()

REGISTRY_NAMES = {
    "regular": "Segoe UI (TrueType)",
    "bold": "Segoe UI Bold (TrueType)",
    "italic": "Segoe UI Italic (TrueType)",
    "bold_italic": "Segoe UI Bold Italic (TrueType)",
    "light": "Segoe UI Light (TrueType)",
    "semilight": "Segoe UI Semilight (TrueType)",
    "semibold": "Segoe UI Semibold (TrueType)",
    "black": "Segoe UI Black (TrueType)",
    "black_italic": "Segoe UI Black Italic (TrueType)",
    "light_italic": "Segoe UI Light Italic (TrueType)",
    "semibold_italic": "Segoe UI Semibold Italic (TrueType)",
    "semilight_italic": "Segoe UI Semilight Italic (TrueType)",
    "variable": "Segoe UI Variable (TrueType)",
    "consolas_regular": "Consolas (TrueType)",
    "consolas_bold": "Consolas Bold (TrueType)",
    "consolas_italic": "Consolas Italic (TrueType)",
    "consolas_bold_italic": "Consolas Bold Italic (TrueType)",
}

WEIGHT_TARGETS = {
    "regular":              (400, False),
    "bold":                 (700, False),
    "italic":               (400, True),
    "bold_italic":          (700, True),
    "light":                (300, False),
    "semilight":            (350, False),
    "semibold":             (600, False),
    "black":                (900, False),
    "black_italic":         (900, True),
    "light_italic":         (300, True),
    "semibold_italic":      (600, True),
    "semilight_italic":     (350, True),
    "consolas_regular":     (400, False),
    "consolas_bold":        (700, False),
    "consolas_italic":      (400, True),
    "consolas_bold_italic": (700, True),
}

def mod_filename(system_file, source_path=None):
    system_path = Path(system_file)
    if source_path:
        ext = Path(source_path).suffix.lower() or ".ttf"
        unique_id = hashlib.sha256(str(Path(source_path).resolve()).encode()).hexdigest()[:6]
    else:
        ext = system_path.suffix.lower() or ".ttf"
        unique_id = uuid.uuid4().hex[:6]
    return f"{system_path.stem}{MANAGED_FONT_SUFFIX}_{unique_id}{ext}"


WPC_REGISTRY_NAMES = {
    "regular": "Segoe WPC (TrueType)",
    "bold": "Segoe WPC Bold (TrueType)",
    "semibold": "Segoe WPC Semibold (TrueType)",
    "light": "Segoe WPC Light (TrueType)",
    "italic": "Segoe WPC Italic (TrueType)",
}


def default_registry_targets(weights=None):
    active_weights = weights if weights is not None else get_system_weights()
    targets = {
        REGISTRY_NAMES[weight]: filename
        for weight, filename in active_weights.items()
        if weight in REGISTRY_NAMES
    }
    for weight, reg_name in WPC_REGISTRY_NAMES.items():
        if weight in active_weights:
            targets[reg_name] = active_weights[weight]
    return targets

