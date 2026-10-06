"""Result table. MVP on top of DataTable; stage 6 replaces the internals, not this API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.text import Text
from textual.widgets import DataTable

from sqlide.db.result import Column
from sqlide.grid.formatting import NULL_TEXT, format_value

MAX_CELL_CHARS = 80
_NUMERIC = (int, float)


class ResultGrid(DataTable):
    def __init__(self, **kw: Any) -> None:
        super().__init__(cursor_type="cell", zebra_stripes=True, show_row_labels=True, **kw)

    def load(self, columns: Sequence[Column], rows: Sequence[tuple[Any, ...]]) -> None:
        from decimal import Decimal

        self.clear(columns=True)
        self.add_columns(*(c.name for c in columns))
        numeric = (*_NUMERIC, Decimal)
        for i, row in enumerate(rows, 1):
            self.add_row(*(_cell(v, numeric) for v in row), label=Text(str(i), style="dim"))


def _cell(value: Any, numeric: tuple[type, ...]) -> Text:
    text = format_value(value)
    if len(text) > MAX_CELL_CHARS:
        text = text[: MAX_CELL_CHARS - 1] + "…"
    if text == NULL_TEXT and value is None:
        return Text(text, style="dim italic")
    if isinstance(value, numeric) and not isinstance(value, bool):
        return Text(text, justify="right")
    return Text(text)
