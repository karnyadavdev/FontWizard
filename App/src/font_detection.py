import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

from settings import FONT_EXTENSIONS, WEIGHTS, WEIGHT_TARGETS


@dataclass
class FontMetadata:
    path: Path
    extension: str
    family_name: str
    full_name: str
    subfamily_name: str
    weight_class: int = 400
    units_per_em: int = 2048
    is_italic: bool = False
    is_variable: bool = False


WEIGHT_REGEX = [
    ("black_italic", re.compile(r"\b(?:black|heavy)\s*(?:italic|oblique)\b")),
    ("semibold_italic", re.compile(r"\b(?:semi\s*bold|semibold|demibold)\s*(?:italic|oblique)\b")),
    ("semilight_italic", re.compile(r"\bsemi\s*light\s*(?:italic|oblique)\b")),
    ("light_italic", re.compile(r"\b(?:light|thin|extra\s*light|extralight)\s*(?:italic|oblique)\b")),
    ("bold_italic", re.compile(r"\b(?:bold|extra\s*bold|extrabold)\s*(?:italic|oblique)\b")),
    ("semibold", re.compile(r"\b(?:semi\s*bold|semibold|demibold)\b")),
    ("semilight", re.compile(r"\bsemi\s*light\b")),
    ("black", re.compile(r"\b(?:black|heavy)\b")),
    ("light", re.compile(r"\b(?:light|thin|extra\s*light|extralight)\b")),
    ("bold", re.compile(r"\b(?:bold|extra\s*bold|extrabold)\b")),
    ("italic", re.compile(r"\b(?:italic|oblique)\b")),
    ("regular", re.compile(r"\b(?:regular|roman|book|normal)\b")),
]


def _tokenize(value):
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", value)
    normalized = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", normalized)
    parts = re.split(r"[^a-z0-9]+", normalized.lower())
    return [part for part in parts if part]


def _normalized_text(*values: str) -> str:
    return " ".join(part for value in values for part in _tokenize(value))


def _clean_family_text(text: str) -> str:
    cleaned = text
    for _, pattern in WEIGHT_REGEX:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"\b(?:medium|regular|roman|book|normal)\b", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def classify_weight_from_strings(*values):
    haystack = _normalized_text(*values)
    for weight, pattern in WEIGHT_REGEX:
        if pattern.search(haystack):
            return weight
    return "regular"


@lru_cache(maxsize=1024)
def _inspect_font_cached(font_path_str: str) -> FontMetadata:
    font_path = Path(font_path_str)
    extension = font_path.suffix.lower()
    if extension not in FONT_EXTENSIONS:
        raise ValueError(f"Unsupported font type: {font_path.suffix}")
    try:
        font = TTFont(font_path)
    except TTLibError as exc:
        raise ValueError(f"Unable to read font: {font_path.name}") from exc

    try:
        if "glyf" not in font or "loca" not in font:
            raise ValueError(f"Choose a TrueType-outline .ttf font: {font_path.name}")

        try:
            weight_class = font["OS/2"].usWeightClass
        except Exception:
            weight_class = 400
        
        try:
            is_italic = bool(font["head"].macStyle & 0x2) or font["post"].italicAngle != 0
        except Exception:
            is_italic = False

        metadata = FontMetadata(
            path=font_path,
            extension=extension,
            family_name=font["name"].getBestFamilyName() or font_path.stem,
            full_name=font["name"].getBestFullName() or font_path.stem,
            subfamily_name=font["name"].getBestSubFamilyName() or "",
            weight_class=weight_class,
            units_per_em=font["head"].unitsPerEm,
            is_italic=is_italic,
            is_variable="fvar" in font,
        )
    finally:
        font.close()
    return metadata


def inspect_font(path: str | os.PathLike[str]) -> FontMetadata:
    return _inspect_font_cached(str(Path(path).resolve()))


def classify_weight(path, metadata=None):
    metadata = metadata or inspect_font(path)
    if metadata.is_variable:
        return "variable"
    return classify_weight_from_strings(
        metadata.path.stem,
        metadata.family_name,
        metadata.full_name,
        metadata.subfamily_name,
    )


def infer_family_label_from_strings(*values):
    for value in values:
        normalized = _clean_family_text(_normalized_text(value))
        if normalized:
            return normalized
    return _clean_family_text(_normalized_text(*values))


def _family_label(path, metadata):
    return infer_family_label_from_strings(metadata.family_name, metadata.full_name, path.stem)


def _same_family(primary_label, candidate_label):
    return primary_label and primary_label == candidate_label


def detect_weight_overrides(primary_path, existing=None):
    primary = Path(primary_path).resolve()
    folder = primary.parent
    primary_metadata = inspect_font(primary)
    primary_family = _family_label(primary, primary_metadata)
    existing = existing or {}
    detected = {}

    candidates = []
    for candidate in folder.iterdir():
        if not candidate.is_file():
            continue
        if candidate.resolve() == primary or candidate.suffix.lower() not in FONT_EXTENSIONS:
            continue
        try:
            metadata = inspect_font(candidate)
        except ValueError:
            continue
        if not _same_family(primary_family, _family_label(candidate, metadata)):
            continue
        candidates.append((candidate, metadata))

    for candidate, metadata in candidates:
        weight = classify_weight(candidate, metadata)
        if not weight or weight == "regular" or existing.get(weight) or weight in detected:
            continue
        detected[weight] = str(candidate)

    unfilled = [
        w for w in WEIGHTS
        if w != "regular" and w != "variable" and w not in existing and w not in detected
    ]
    nearest_candidates = [(primary, primary_metadata), *candidates]
    if unfilled and nearest_candidates:
        for target_weight in unfilled:
            target_value, target_italic = WEIGHT_TARGETS[target_weight]

            best_path = None
            best_distance = float("inf")
            best_weight = -1

            for candidate, metadata in nearest_candidates:
                if metadata.is_variable or metadata.is_italic != target_italic:
                    continue
                distance = abs(metadata.weight_class - target_value)
                if distance < best_distance or (distance == best_distance and metadata.weight_class > best_weight):
                    best_distance = distance
                    best_weight = metadata.weight_class
                    best_path = str(candidate)

            if best_path is not None:
                detected[target_weight] = best_path

    return detected
