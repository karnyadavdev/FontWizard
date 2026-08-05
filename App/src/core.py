from dataclasses import dataclass

from pathlib import Path

from settings import CONSOLAS_WEIGHTS, WEIGHTS
from paths import RuntimePaths
from checks import PreflightService
from font_detection import detect_mono_font_in_folder, detect_weight_overrides, inspect_font
from journal import JOURNAL_FILENAME, OperationJournal
from operation import FontWorkflow, detect_mono_family
from app_state import iso_now, ManagedStateStore

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
        self.selection = SelectionState(
            paths={w: None for w in WEIGHTS},
            labels={w: "unset" for w in WEIGHTS},
        )
        self.monospace_paths = {weight: None for weight in CONSOLAS_WEIGHTS}
        self.monospace_last_pick = None

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
                "Variable fonts are not supported. Choose a static .ttf font"
            )

        paths = self.selection.paths
        labels = self.selection.labels
        manual_paths = {
            weight: font_path
            for weight, font_path in paths.items()
            if weight != "regular" and labels.get(weight) == "manual"
        }
        manual_paths["regular"] = path
        detected = detect_weight_overrides(path, manual_paths)

        paths["regular"] = path
        labels["regular"] = "manual"
        for weight in WEIGHTS:
            if weight == "regular" or labels.get(weight) == "manual":
                continue
            detected_path = detected.get(weight)
            paths[weight] = detected_path or path
            labels[weight] = "auto-detected"

        if not any(self.monospace_paths.values()):
            mono = detect_mono_font_in_folder(path)
            self.monospace_last_pick = str(Path(mono).resolve()) if mono else None

    def apply(self, progress=None):
        regular_path = self.selection.paths.get("regular")
        return self.workflow.apply(
            self.selection.paths,
            self.selection.labels,
            monospace_paths=self.effective_monospace_paths(regular_path),
            progress=progress,
        )

    def restore(self, progress=None):
        return self.workflow.restore(progress=progress)

    def set_monospace_style(self, weight, path):
        metadata = inspect_font(path)
        if metadata.is_variable:
            raise ValueError(
                "Variable fonts are not supported. Choose a static .ttf font"
            )
        self.monospace_paths[weight] = str(Path(path).resolve())
        self.monospace_last_pick = str(Path(path).resolve())

    def clear_monospace_style(self, weight):
        self.monospace_paths[weight] = None
        if not any(self.monospace_paths.values()):
            self.monospace_last_pick = None

    def effective_monospace_paths(self, regular_path):
        base = detect_mono_family(self.monospace_last_pick) if self.monospace_last_pick else {}
        paths = {}
        for weight in CONSOLAS_WEIGHTS:
            if self.monospace_paths.get(weight):
                paths[weight] = self.monospace_paths[weight]
            elif base.get(weight):
                paths[weight] = base[weight]
            else:
                paths[weight] = regular_path
        return paths

    def recover_pending_operation(self) -> list[str]:
        journal = OperationJournal(self.paths.data_root / JOURNAL_FILENAME)
        data = journal.load()
        if not data:
            return []

        warnings = []
        kind = data.get("kind")
        try:
            if kind == "apply":
                inputs = data.get("inputs", {})
                result = self.workflow.apply(
                    inputs.get("selection") or {},
                    inputs.get("source_labels"),
                    monospace_paths=self._recover_monospace_paths(inputs),
                )
            elif kind == "restore":
                result = self.workflow.restore()
            else:
                journal.clear()
                return warnings
            warnings.extend(result.warnings)
            if not result.success:
                warnings.append(
                    f"Automatic recovery could not finish the pending operation: {result.message}"
                )
            journal.clear()
            self._log_recovery_outcome(kind, result.success, result.message, result.warnings)
        except Exception as exc:
            journal.clear()
            message = f"Automatic recovery could not finish the pending operation: {exc}"
            warnings.append(message)
            self._log_recovery_outcome(kind, False, message, [])
        return warnings

    def _recover_monospace_paths(self, inputs):
        monospace_paths = inputs.get("monospace_paths")
        if monospace_paths:
            return {w: p for w, p in monospace_paths.items() if p}
        legacy_base = inputs.get("monospace_font_path")
        if legacy_base:
            return detect_mono_family(legacy_base)
        return {}

    def _log_recovery_outcome(self, kind, success, message, details):
        try:
            status = "finished" if success else "failed"
            with (self.paths.log_root / "apply.log").open("a", encoding="utf-8") as handle:
                handle.write(f"{iso_now()} recovery ({kind}) {status}: {message}\n")
                for detail in details:
                    handle.write(f"{iso_now()} recovery detail: {detail}\n")
        except OSError:
            pass

    def sweep_stale_temp_dirs(self) -> list[str]:
        from operation_files import sweep_stale_temp_dirs

        journal = OperationJournal(self.paths.data_root / JOURNAL_FILENAME).load()
        keep = set(journal.get("temp_dirs", [])) if journal else set()
        warnings, _ = sweep_stale_temp_dirs(self.paths.temp_root, keep=keep)
        return warnings
