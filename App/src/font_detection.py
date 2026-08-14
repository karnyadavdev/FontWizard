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
    is_monospace: bool = False


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

        try:
            is_mono = bool(font["post"].isFixedPitch != 0)
        except Exception:
            is_mono = False

        if not is_mono:
            try:
                panose = getattr(font["OS/2"], "panose", None)
                if panose and getattr(panose, "bProportion", 0) == 9:
                    is_mono = True
            except Exception:
                pass

        family_name = font["name"].getBestFamilyName() or font_path.stem
        full_name = font["name"].getBestFullName() or font_path.stem
        subfamily_name = font["name"].getBestSubFamilyName() or ""

        if not is_mono:
            combined = f"{font_path.stem} {family_name} {full_name}".lower()
            if any(term in combined for term in ("mono", "code", "console", "typewriter")):
                is_mono = True

        metadata = FontMetadata(
            path=font_path,
            extension=extension,
            family_name=family_name,
            full_name=full_name,
            subfamily_name=subfamily_name,
            weight_class=weight_class,
            units_per_em=font["head"].unitsPerEm,
            is_italic=is_italic,
            is_variable="fvar" in font,
            is_monospace=is_mono,
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


def _score_candidate(candidate, metadata, target_weight, target_value, target_italic, is_mono_target, primary_metadata, primary_root):
    score = 0

    if is_mono_target:
        if metadata.is_monospace:
            score += 20000
    else:
        if metadata.is_monospace == primary_metadata.is_monospace:
            score += 5000

    cand_name = _clean_family_text(_normalized_text(metadata.family_name, metadata.full_name, candidate.stem))
    if primary_root and primary_root in cand_name:
        score += 3000

    if metadata.is_italic == target_italic:
        score += 10000
    else:
        score -= 5000

    score -= abs(metadata.weight_class - target_value)

    norm_stem = _normalized_text(candidate.stem, metadata.subfamily_name)
    target_clean = target_weight.replace("consolas_", "").replace("_", " ")
    for kw in target_clean.split():
        if kw in norm_stem:
            score += 250

    return score


def detect_weight_overrides(primary_path, existing=None, weights=None, manual_overrides=None):
    from settings import get_system_weights
    active_weights = weights if weights is not None else get_system_weights()
    primary = Path(primary_path).resolve()
    folder = primary.parent
    primary_metadata = inspect_font(primary)
    primary_family = _family_label(primary, primary_metadata)
    primary_root = _tokenize(primary_family)[0] if _tokenize(primary_family) else ""
    existing = existing or {}
    manual_overrides = manual_overrides or {}
    detected = {}

    all_candidates = []
    for candidate in folder.iterdir():
        if not candidate.is_file() or candidate.suffix.lower() not in FONT_EXTENSIONS:
            continue
        try:
            metadata = inspect_font(candidate)
        except ValueError:
            continue
        if not metadata.is_variable:
            all_candidates.append((candidate, metadata))

    if (primary, primary_metadata) not in all_candidates:
        all_candidates.append((primary, primary_metadata))

    for target_weight in active_weights:
        if target_weight == "variable":
            continue
        if target_weight in manual_overrides and manual_overrides[target_weight]:
            override_path = Path(manual_overrides[target_weight])
            if override_path.exists():
                detected[target_weight] = str(override_path.resolve())
                continue

        if target_weight in existing and existing[target_weight]:
            continue

        if target_weight not in WEIGHT_TARGETS:
            continue

        target_value, target_italic = WEIGHT_TARGETS[target_weight]
        is_mono_target = target_weight.startswith("consolas_")

        best_cand = None
        best_score = float("-inf")

        for candidate, metadata in all_candidates:
            score = _score_candidate(
                candidate,
                metadata,
                target_weight,
                target_value,
                target_italic,
                is_mono_target,
                primary_metadata,
                primary_root,
            )
            if score > best_score:
                best_score = score
                best_cand = candidate

        if best_cand is not None:
            detected[target_weight] = str(best_cand.resolve())
        else:
            detected[target_weight] = str(primary)

    return detected



