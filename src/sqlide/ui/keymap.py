"""Catalogue of rebindable keys, read from the BINDINGS of the UI classes.

Defaults come from the class BINDINGS; keymap.toml overrides are applied on top, so help,
`sqlide keys` and the toolbar tooltips always show the keys that really work.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding

from sqlide.app import SqlideApp
from sqlide.config.keymap import load_keymap
from sqlide.ui.screens.main import MainScreen
from sqlide.ui.widgets.console_tab import ConsoleTab
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.schema_tree import SchemaTree
from sqlide.ui.widgets.sql_editor import SqlEditor

SOURCES = (SqlideApp, MainScreen, SqlEditor, ConsoleTab, SchemaTree, ResultGrid)

_NAMES = {
    "escape": "Esc",
    "enter": "Enter",
    "space": "Space",
    "slash": "/",
    "underscore": "_",
    "at": "@",
    "pageup": "PgUp",
    "pagedown": "PgDn",
    "delete": "Del",
    "backspace": "Bksp",
    "left": "←",
    "right": "→",
    "up": "↑",
    "down": "↓",
}


@dataclass(frozen=True, slots=True)
class KeyInfo:
    id: str
    keys: str  # effective keys, comma separated (override or default)
    description: str
    default: str = ""

    @property
    def overridden(self) -> bool:
        return self.keys != self.default


def format_key(key: str) -> str:
    """`ctrl+shift+f5` -> `Ctrl+Shift+F5`; one key, as people write it."""
    parts = []
    for part in key.strip().split("+"):
        if part in ("ctrl", "alt", "shift", "super"):
            parts.append(part.capitalize())
        elif part in _NAMES:
            parts.append(_NAMES[part])
        else:
            parts.append(part.upper() if len(part) <= 2 or part[0] == "f" else part.capitalize())
    return "+".join(parts)


def format_keys(keys: str, limit: int = 0) -> str:
    """Comma separated keys -> `Ctrl+J / F5`; `limit` keeps only the first N (0 = all)."""
    items = [format_key(k) for k in keys.split(",") if k.strip()]
    return " / ".join(items[:limit] if limit else items)


def catalogue(overrides: dict[str, str] | None = None) -> list[KeyInfo]:
    """Every rebindable action with its effective keys (overrides default to keymap.toml)."""
    overrides = load_keymap() if overrides is None else overrides
    out = []
    for cls in SOURCES:
        for b in cls.BINDINGS:  # type: ignore[attr-defined]
            if isinstance(b, Binding) and b.id:
                out.append(KeyInfo(b.id, overrides.get(b.id, b.key), b.description, b.key))
    return out


def keys_for(action_id: str, overrides: dict[str, str] | None = None, limit: int = 1) -> str:
    """Display string for one action id (empty when unknown)."""
    for info in catalogue(overrides):
        if info.id == action_id:
            return format_keys(info.keys, limit)
    return ""
