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

        system_weights = self.workflow._system_weights()
        paths = self.selection.paths
        labels = self.selection.labels
        manual_paths = {
            weight: font_path
            for weight, font_path in paths.items()
            if weight != "regular" and labels.get(weight) == "manual"
        }
        manual_paths["regular"] = path
        detected = detect_weight_overrides(path, manual_paths, weights=system_weights)

        paths["regular"] = path
        labels["regular"] = "manual"
        for weight in system_weights:
            if weight == "regular" or labels.get(weight) == "manual":
                continue
            detected_path = detected.get(weight)
            paths[weight] = detected_path or path
            labels[weight] = "auto-detected"

    def set_card_override(self, weight, path):
        metadata = inspect_font(path)
        if metadata.is_variable:
            raise ValueError(
                "Variable fonts are not supported. Choose a static .ttf file instead."
            )
        self.selection.paths[weight] = str(Path(path).resolve())
        self.selection.labels[weight] = "manual"

    def reset_card_override(self, weight):
        if weight == "regular":
            return
        self.selection.labels[weight] = "unset"
        regular_path = self.selection.paths.get("regular")
        if regular_path:
            self.set_regular_font(regular_path)

    def apply(self, progress=None):
        return self.workflow.apply(
            self.selection.paths,
            self.selection.labels,
            progress=progress,
        )

    def restore(self, progress=None):
        return self.workflow.restore(progress=progress)

