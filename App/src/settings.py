import os
from pathlib import Path
import uuid
import hashlib

APP_NAME = "Font Wizard"
APP_GITHUB_URL = "https://github.com/karnyadavdev"
SCHEMA_VERSION = 1

SUPPORTED_WINDOWS_MAJOR = 10
WINDOWS_11_BUILD = 22000

FONT_EXTENSIONS = {".ttf"}
MANAGED_FONT_SUFFIX = "_fontwizard"

FONT_REGISTRY_SUBKEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

FONTS_DIR = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"

WEIGHTS = {
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
    "variable": "SegUIVar.ttf",
}

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
}

WEIGHT_TARGETS = {
    "regular":          (400, False),
    "bold":             (700, False),
    "italic":           (400, True),
    "bold_italic":      (700, True),
    "light":            (300, False),
    "semilight":        (350, False),
    "semibold":         (600, False),
    "black":            (900, False),
    "black_italic":     (900, True),
    "light_italic":     (300, True),
    "semibold_italic":  (600, True),
    "semilight_italic": (350, True),
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


def default_registry_targets():
    return {
        REGISTRY_NAMES[weight]: filename
        for weight, filename in WEIGHTS.items()
    }
