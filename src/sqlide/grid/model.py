"""Table state behind the result grid: rows, multi-column sort, filter, paging. Pure Python."""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from sqlide.db.result import Column
from sqlide.grid.formatting import format_value

Row = tuple[Any, ...]


def _sort_key(v: Any) -> tuple[int, Any]:
    """Orders values of mixed types without ever raising (NULLs are handled by the caller)."""
    if isinstance(v, bool | int | float | Decimal):
        return (0, v if v == v else float("-inf"))  # NaN sorts first
    if isinstance(v, dt.datetime):
        return (1, v)
    if isinstance(v, dt.date):
        return (2, v)
    if isinstance(v, dt.time):
        return (3, v)
    if isinstance(v, bytes):
        return (4, v)
    return (5, str(v).casefold())


class GridModel:
    def __init__(self, columns: Sequence[Column], rows: Iterable[Row] = ()) -> None:
        self.columns = list(columns)
        self._rows: list[Row] = list(rows)
        self._view: list[int] = list(range(len(self._rows)))
        self._search: list[str | None] = [None] * len(self._rows)
        self.sort: list[tuple[int, bool]] = []  # (column, descending), most significant first
        self.filter_text = ""

    # --- reading ---
    def __len__(self) -> int:
        return len(self._view)

    @property
    def total_rows(self) -> int:
        return len(self._rows)

    def loaded_rows(self) -> list[Row]:
        """Every loaded row in arrival order (ignores sort and filter)."""
        return list(self._rows)

    def row(self, view_row: int) -> Row:
        return self._rows[self._view[view_row]]

    def value(self, view_row: int, col: int) -> Any:
        return self._rows[self._view[view_row]][col]

    def rows(self, first: int, last: int) -> list[Row]:
        """View rows first..last inclusive."""
        return [self._rows[i] for i in self._view[first : last + 1]]

    # --- changing ---
    def append(self, rows: Sequence[Row]) -> None:
        start = len(self._rows)
        self._rows.extend(rows)
        self._search.extend([None] * len(rows))
        if self.sort or self.filter_text:
            self._rebuild()
        else:
            self._view.extend(range(start, len(self._rows)))

    def set_filter(self, text: str) -> None:
        self.filter_text = text.strip()
        self._rebuild()

    def cycle_sort(self, col: int, add: bool = False) -> None:
        """none -> ascending -> descending -> none. `add` keeps other sort columns."""
        current = dict(self.sort).get(col)
        new = {None: False, False: True, True: None}[current]
        others = [(c, d) for c, d in self.sort if c != col] if add else []
        if new is None:
            self.sort = others
        elif add and current is not None:
            self.sort = [(c, new if c == col else d) for c, d in self.sort]
        else:
            self.sort = [*others, (col, new)]
        self._rebuild()

    def sort_state(self, col: int) -> tuple[bool, int] | None:
        """(descending, 1-based priority) or None if the column is not sorted."""
        for rank, (c, desc) in enumerate(self.sort, 1):
            if c == col:
                return desc, rank
        return None

    # --- internals ---
    def _matches(self, i: int, needle: str) -> bool:
        text = self._search[i]
        if text is None:
            text = self._search[i] = "\x00".join(format_value(v).lower() for v in self._rows[i])
        return needle in text

    def _rebuild(self) -> None:
        idx = list(range(len(self._rows)))
        if self.filter_text:
            needle = self.filter_text.lower()
            idx = [i for i in idx if self._matches(i, needle)]
        for col, desc in reversed(self.sort):  # stable sorts, least significant key first
            present = [i for i in idx if self._rows[i][col] is not None]
            nulls = [i for i in idx if self._rows[i][col] is None]
            present.sort(key=lambda i, c=col: _sort_key(self._rows[i][c]), reverse=desc)
            idx = present + nulls  # NULLs last in both directions
        self._view = idx
