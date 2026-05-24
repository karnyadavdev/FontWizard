from dataclasses import dataclass, field
from pathlib import Path

from font_detection import inspect_font
from settings import REGISTRY_NAMES, WEIGHTS, mod_filename

@dataclass
class FontPlanEntry:
    weight: str
    source_path: Path
    source_label: str
    system_filename: str
    registry_name: str
    generated_filename: str
    family_name: str
    full_name: str


@dataclass
class ValidationSummary:
    entries: list[FontPlanEntry] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self):
        return not self.errors and bool(self.entries)


def resolve_font_selection(selection):
    regular_path = selection.get("regular")
    if not regular_path:
        return {}

    resolved = {}
    for weight in WEIGHTS:
        resolved[weight] = selection.get(weight) or regular_path
    return resolved


def validate_selection(selection, source_labels=None):
    summary = ValidationSummary()
    resolved = resolve_font_selection(selection)
    if not resolved:
        summary.errors.append("Choose a regular font to continue.")
        return summary

    metadata_cache = {}
    family_names = set()
    variable_rejections = set()
    invalid_source_rejections = set()
    source_labels = source_labels or {}

    for weight, source in resolved.items():
        source_path = Path(source)
        if not source_path.exists():
            summary.errors.append(f"Font file not found for {weight.replace('_', ' ')}.")
            continue
        cache_key = str(source_path.resolve())
        if cache_key not in metadata_cache:
            try:
                metadata_cache[cache_key] = inspect_font(source_path)
            except ValueError as exc:
                if cache_key not in invalid_source_rejections:
                    ext = source_path.suffix.lower()
                    if ext == ".otf":
                        summary.errors.append(
                            f"OpenType (.otf) fonts are not supported. "
                            f"Segoe UI replacement requires TrueType (.ttf) files. "
                            f"File: {source_path.name}"
                        )
                    elif ext != ".ttf":
                        summary.errors.append(
                            f"This file type ({ext}) is not supported. "
                            f"Choose a .ttf font file."
                        )
                    else:
                        summary.errors.append(str(exc))
                    invalid_source_rejections.add(cache_key)
                continue

        metadata = metadata_cache[cache_key]
        if metadata.is_variable:
            if cache_key not in variable_rejections:
                summary.errors.append(
                    "Variable fonts are not supported. Choose a static .ttf file instead."
                )
                variable_rejections.add(cache_key)
            continue


        family_names.add(metadata.family_name)
        summary.entries.append(
            FontPlanEntry(
                weight=weight,
                source_path=metadata.path,
                source_label=source_labels.get(weight, "resolved"),
                system_filename=WEIGHTS[weight],
                registry_name=REGISTRY_NAMES[weight],
                generated_filename=mod_filename(WEIGHTS[weight], metadata.path),
                family_name=metadata.family_name,
                full_name=metadata.full_name,
            )
        )

    if len(family_names) > 1:
        summary.warnings.append(
            "The selected styles come from more than one font family. Review them carefully before applying."
        )

    return summary
