"""Catalogue of rebindable keys, read from the BINDINGS of the UI classes."""

from __future__ import annotations

from dataclasses import dataclass

from textual.binding import Binding

from sqlide.app import SqlideApp
from sqlide.ui.screens.main import MainScreen
from sqlide.ui.widgets.console_tab import ConsoleTab
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.schema_tree import SchemaTree
from sqlide.ui.widgets.sql_editor import SqlEditor

SOURCES = (SqlideApp, MainScreen, SqlEditor, ConsoleTab, SchemaTree, ResultGrid)


@dataclass(frozen=True, slots=True)
class KeyInfo:
    id: str
    keys: str
    description: str


def catalogue() -> list[KeyInfo]:
    out = []
    for cls in SOURCES:
        for b in cls.BINDINGS:  # type: ignore[attr-defined]
            if isinstance(b, Binding) and b.id:
                out.append(KeyInfo(b.id, b.key, b.description))
    return out
