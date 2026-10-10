"""Dialogs opened from the result grid: copy-as menu and full value viewer."""

from __future__ import annotations

import json
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, TextArea
from textual.widgets.option_list import Option

COPY_FORMATS: list[tuple[str, str]] = [
    ("tsv", "Values (TSV)"),
    ("tsv_header", "Values with header (TSV)"),
    ("csv", "CSV with header"),
    ("markdown", "Markdown table"),
    ("json", "JSON"),
    ("insert", "SQL INSERT statements"),
    ("cell", "Current cell value"),
]


class CopyMenu(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "dismiss_none", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label("Copy selection as", classes="title")
            yield OptionList(*(Option(label, id=key) for key, label in COPY_FORMATS))

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.dismiss(event.option.id)

    def action_dismiss_none(self) -> None:
        self.dismiss(None)


def pretty_if_json(text: str) -> tuple[str, bool]:
    """Pretty-print text that is a JSON object/array; otherwise return it unchanged."""
    stripped = text.strip()
    if stripped[:1] in "{[":
        try:
            return json.dumps(json.loads(stripped), indent=2, ensure_ascii=False), True
        except ValueError:
            pass
    return text, False


class ValueViewer(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,q", "close", "Close"),
        Binding("c", "copy", "Copy"),
    ]

    def __init__(self, title: str, text: str) -> None:
        super().__init__()
        self._title = title
        self._text, self._is_json = pretty_if_json(text)

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog viewer"):
            yield Label(self._title, classes="title")
            yield TextArea(
                self._text,
                read_only=True,
                language="json" if self._is_json else None,
                show_line_numbers=True,
                soft_wrap=True,
                id="value",
            )
            yield Label("c copy · esc close", classes="hint")

    def on_mount(self) -> None:
        self.query_one("#value", TextArea).focus()

    def action_close(self) -> None:
        self.dismiss(None)

    def action_copy(self) -> None:
        from sqlide import clipboard

        name = clipboard.copy(self._text, self.app)
        self.app.notify(f"Copied value ({name})")


def describe_cell(column: str, type_name: str, value: Any) -> str:
    return f"{column}  ·  {type_name}" + ("  ·  NULL" if value is None else "")
