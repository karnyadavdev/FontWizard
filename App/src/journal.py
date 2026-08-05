import json
import os
import uuid
from pathlib import Path

JOURNAL_SCHEMA_VERSION = 1
JOURNAL_FILENAME = "operation_journal.json"


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f".{path.name}.{uuid.uuid4().hex[:8]}.tmp"
    try:
        temp.write_text(text, encoding="utf-8")
        os.replace(temp, path)
    except OSError:
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


class OperationJournal:
    def __init__(self, path):
        self.path = Path(path)
        self._data = None

    def load(self):
        if not self.path.exists():
            return None
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        if not isinstance(data, dict) or data.get("schema_version") != JOURNAL_SCHEMA_VERSION:
            return None
        return data

    def begin(self, kind, inputs, previous_registry, temp_dirs=None):
        data = {
            "schema_version": JOURNAL_SCHEMA_VERSION,
            "kind": kind,
            "inputs": inputs,
            "previous_registry": previous_registry,
            "temp_dirs": temp_dirs or [],
        }
        self._write(data)

    def add_temp_dir(self, path):
        data = self._read()
        if not data:
            return
        value = str(Path(path).resolve())
        if value not in data.setdefault("temp_dirs", []):
            data["temp_dirs"].append(value)
            self._write(data)

    def record_step(self, name):
        data = self._read()
        if not data:
            return
        steps = data.setdefault("steps", [])
        if name not in steps:
            steps.append(name)
            self._write(data)

    def clear(self):
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            pass
        self._data = None

    def _read(self):
        if self._data is None:
            self._data = self.load()
        return self._data

    def _write(self, data):
        atomic_write_text(self.path, json.dumps(data, indent=2, sort_keys=True))
        self._data = data
