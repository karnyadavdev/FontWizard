import hashlib
import json
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from settings import APP_NAME, SCHEMA_VERSION


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def hash_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_empty_state():
    return {
        "schema_version": SCHEMA_VERSION,
        "app_name": APP_NAME,
        "install": {
            "status": "clean",
            "registry_targets": {},
            "fonts": {},
            "previous_registry": {},
            "applied_at": None,
            "restored_at": None,
        },
        "last_action": {
            "kind": "startup",
            "status": "unknown",
            "timestamp": iso_now(),
            "details": "",
        },
    }


def validate_state(state):
    if not isinstance(state, dict):
        return False
    return (
        isinstance(state.get("schema_version"), int)
        and state.get("schema_version") == SCHEMA_VERSION
        and isinstance(state.get("install"), dict)
        and isinstance(state.get("last_action"), dict)
    )


class ManagedStateStore:
    def __init__(self, state_path: str | Path):
        self.state_path = Path(state_path)

    def load(self):
        if not self.state_path.exists():
            return None
        try:
            with self.state_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError):
            return None
        return data if validate_state(data) else None

    def save(self, state):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)

    def load_or_empty(self):
        state = self.load()
        return deepcopy(state) if state else build_empty_state()
