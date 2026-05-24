import os
from dataclasses import dataclass
from pathlib import Path

from settings import APP_NAME


@dataclass(frozen=True)
class RuntimePaths:
    source_root: Path
    project_root: Path

    data_root: Path
    local_root: Path
    managed_font_root: Path
    pending_ops_root: Path
    log_root: Path
    temp_root: Path
    state_path: Path

    @classmethod
    def discover(cls):
        source_root = Path(__file__).resolve().parent
        project_root = source_root.parent

        program_data = os.environ.get("FONTWIZARD_DATA_DIR")
        if program_data:
            data_root = Path(program_data)
        else:
            data_root = Path(os.environ.get("PROGRAMDATA", project_root)) / APP_NAME

        local_data = os.environ.get("FONTWIZARD_LOCAL_DIR")
        if local_data:
            local_root = Path(local_data)
        else:
            local_root = Path(os.environ.get("LOCALAPPDATA", project_root)) / APP_NAME

        return cls(
            source_root=source_root,
            project_root=project_root,

            data_root=data_root,
            local_root=local_root,
            managed_font_root=data_root / "managed_fonts",
            pending_ops_root=data_root / "managed_fonts" / "pending_ops",
            log_root=local_root / "logs",
            temp_root=local_root / "temp",
            state_path=data_root / "state.json",
        )

    def ensure_runtime_dirs(self):
        for path in (
            self.data_root,
            self.local_root,
            self.managed_font_root,
            self.pending_ops_root,
            self.log_root,
            self.temp_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def make_temp_dir(self, prefix):
        import tempfile
        self.ensure_runtime_dirs()
        return Path(tempfile.mkdtemp(prefix=prefix, dir=self.temp_root))
