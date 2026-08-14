from dataclasses import dataclass
from pathlib import Path

from paths import RuntimePaths
from checks import PreflightService
from font_detection import detect_weight_overrides, inspect_font
from operation import FontWorkflow
from app_state import ManagedStateStore
from win_registry import WindowsFontRegistry


@dataclass
class SelectionState:
    paths: dict
    labels: dict


class FontWizardController:
    def __init__(self):
        self.paths = RuntimePaths.discover()
        self.paths.ensure_runtime_dirs()

        self.state_store = ManagedStateStore(self.paths.state_path)
        self.registry = WindowsFontRegistry()
        self.preflight = PreflightService(self.paths, self.registry, self.state_store)
        self.workflow = FontWorkflow(
            self.paths,
            self.registry,
            self.state_store,
            self.preflight,
        )
        system_weights = self.workflow._system_weights()
        self.selection = SelectionState(
            paths={w: None for w in system_weights},
            labels={w: "unset" for w in system_weights},
        )

    def refresh_preflight(self):
        report = self.preflight.collect()

        if report.install_state == "clean" and report.managed_state_valid:
            state = self.state_store.load()
            if state and state.get("install", {}).get("status") == "pending_reboot":
                state["install"]["status"] = "clean"
                try:
                    self.state_store.save(state)
                except OSError as exc:
                    import logging
                    logging.getLogger(__name__).warning("Failed to save state during preflight refresh: %s", exc)

        return report

    def set_regular_font(self, path):
        metadata = inspect_font(path)
        if metadata.is_variable:
            raise ValueError(
                "Variable fonts are not supported. Choose a static .ttf file instead."
            )

        resolved_path = str(Path(path).resolve())
        self.primary_font_path = resolved_path
        system_weights = self.workflow._system_weights()
        paths = self.selection.paths
        labels = self.selection.labels

        detected = detect_weight_overrides(resolved_path, weights=system_weights)

        paths["regular"] = resolved_path
        labels["regular"] = "primary"
        for weight in system_weights:
            if weight == "regular":
                continue
            detected_path = detected.get(weight)
            paths[weight] = detected_path or resolved_path
            labels[weight] = "auto-detected"

    def set_card_override(self, weight, path):
        metadata = inspect_font(path)
        if metadata.is_variable:
            raise ValueError(
                "Variable fonts are not supported. Choose a static .ttf file instead."
            )
        resolved_path = str(Path(path).resolve())
        self.selection.paths[weight] = resolved_path
        self.selection.labels[weight] = "manual"

        if weight.startswith("consolas_"):
            from settings import CONSOLAS_WEIGHTS
            detected_mono = detect_weight_overrides(resolved_path, weights=CONSOLAS_WEIGHTS)
            for mono_weight in CONSOLAS_WEIGHTS:
                if mono_weight != weight and self.selection.labels.get(mono_weight) != "manual":
                    if mono_weight in detected_mono:
                        self.selection.paths[mono_weight] = detected_mono[mono_weight]
                        self.selection.labels[mono_weight] = "auto-detected"

    def reset_card_override(self, weight):
        primary_path = getattr(self, "primary_font_path", None) or self.selection.paths.get("regular")
        if not primary_path:
            return

        system_weights = self.workflow._system_weights()

        if weight == "regular":
            self.selection.paths["regular"] = primary_path
            self.selection.labels["regular"] = "primary"
            return

        if weight == "consolas_regular":
            from settings import CONSOLAS_WEIGHTS
            self.selection.labels["consolas_regular"] = "auto-detected"
            detected_from_primary = detect_weight_overrides(primary_path, weights=CONSOLAS_WEIGHTS)
            for mono_weight in CONSOLAS_WEIGHTS:
                if mono_weight == "consolas_regular" or self.selection.labels.get(mono_weight) != "manual":
                    self.selection.paths[mono_weight] = detected_from_primary.get(mono_weight) or primary_path
                    self.selection.labels[mono_weight] = "auto-detected"
            return

        if weight.startswith("consolas_"):
            from settings import CONSOLAS_WEIGHTS
            if self.selection.labels.get("consolas_regular") == "manual" and self.selection.paths.get("consolas_regular"):
                mono_root = self.selection.paths["consolas_regular"]
                detected_mono = detect_weight_overrides(mono_root, weights=CONSOLAS_WEIGHTS)
                self.selection.paths[weight] = detected_mono.get(weight) or mono_root
            else:
                detected_from_primary = detect_weight_overrides(primary_path, weights={weight: system_weights.get(weight)})
                self.selection.paths[weight] = detected_from_primary.get(weight) or primary_path
            self.selection.labels[weight] = "auto-detected"
            return

        detected = detect_weight_overrides(primary_path, weights={weight: system_weights.get(weight)})
        self.selection.paths[weight] = detected.get(weight) or primary_path
        self.selection.labels[weight] = "auto-detected"

    def apply(self, progress=None):
        return self.workflow.apply(
            self.selection.paths,
            self.selection.labels,
            progress=progress,
        )

    def restore(self, progress=None):
        return self.workflow.restore(progress=progress)

