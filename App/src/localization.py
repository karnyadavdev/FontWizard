"""Translate interface text using the user's preferred display language."""

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import QLocale


_catalog = {}


def configure_language(language=None):
    global _catalog
    if language is None:
        preferred = QLocale.system().uiLanguages()
        language = os.environ.get("FONTWIZARD_LANGUAGE") or next(iter(preferred), "en")
    locale = QLocale(language)
    _catalog = {}
    if locale.language() != QLocale.Language.Chinese:
        return
    script = "Hant" if locale.script() == QLocale.Script.TraditionalHanScript else "Hans"
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    path = root / "assets" / "translations" / f"zh_{script}.json"
    with path.open(encoding="utf-8") as handle:
        _catalog = json.load(handle)


class Message(str):
    """Keep a diagnostic readable in logs while retaining its translatable template."""

    def __new__(cls, template, **values):
        obj = super().__new__(cls, template.format(**values))
        obj.template = template
        obj.values = values
        return obj


def tr(source, **values):
    if isinstance(source, Message):
        values = source.values
        source = source.template
    text = _catalog.get(source, source)
    return text.format(**values) if values else text
