"""Result table: sticky header, row numbers, multi-sort, selection, copy, paging."""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from rich.segment import Segment
from rich.style import Style
from textual import events
from textual.binding import Binding
from textual.geometry import Size
from textual.message import Message
from textual.scroll_view import ScrollView
from textual.strip import Strip

from sqlide import clipboard
from sqlide.db.result import Column, DbError, RowSource
from sqlide.grid import copyfmt
from sqlide.grid.formatting import NULL_TEXT, format_value, raw_text
from sqlide.grid.model import GridModel
from sqlide.ui.screens.grid_dialogs import CopyMenu, ValueViewer, describe_cell

MIN_COL, MAX_COL, SAMPLE_ROWS = 4, 60, 200
LOAD_AHEAD = 30  # start fetching the next page when the cursor is this close to the end
_NUMERIC = (int, float, Decimal)


class ResultGrid(ScrollView, can_focus=True):
    COMPONENT_CLASSES = {
        "result-grid--header",
        "result-grid--gutter",
        "result-grid--cursor",
        "result-grid--selection",
        "result-grid--stripe",
        "result-grid--null",
        "result-grid--sep",
    }
    DEFAULT_CSS = """
    ResultGrid { height: 1fr; }
    ResultGrid > .result-grid--header { background: $primary 35%; text-style: bold; }
    ResultGrid > .result-grid--gutter { color: $text-muted; background: $surface; }
    ResultGrid > .result-grid--cursor { background: $accent; color: $text; text-style: bold; }
    ResultGrid > .result-grid--selection { background: $primary 45%; }
    ResultGrid > .result-grid--stripe { background: $boost; }
    ResultGrid > .result-grid--null { color: $text-muted; text-style: italic; }
    ResultGrid > .result-grid--sep { color: $primary-darken-2; }
    """
    BINDINGS = [
        Binding("up", "move(-1, 0)", show=False),
        Binding("down", "move(1, 0)", show=False),
        Binding("left", "move(0, -1)", show=False),
        Binding("right", "move(0, 1)", show=False),
        Binding("shift+up", "move(-1, 0, True)", show=False),
        Binding("shift+down", "move(1, 0, True)", show=False),
        Binding("shift+left", "move(0, -1, True)", show=False),
        Binding("shift+right", "move(0, 1, True)", show=False),
        Binding("pageup", "page(-1)", show=False),
        Binding("pagedown", "page(1)", show=False),
        Binding("home", "row_edge(0)", show=False),
        Binding("end", "row_edge(1)", show=False),
        Binding("ctrl+home", "grid_edge(0)", show=False),
        Binding("ctrl+end", "grid_edge(1)", show=False),
        Binding("ctrl+a", "select_all", "Select all", show=False, id="grid.select_all"),
        Binding("s", "sort(False)", "Sort", id="grid.sort"),
        Binding("S", "sort(True)", "Add sort", show=False),
        Binding("ctrl+c", "copy", "Copy", id="grid.copy"),
        Binding("y", "copy_menu", "Copy as…", id="grid.copy_menu"),
        Binding("enter", "view_value", "View value", id="grid.view_value"),
        Binding("ctrl+f,slash", "filter", "Filter", id="grid.filter"),
        Binding("l", "load_more", "More rows", show=False, id="grid.load_more"),
        Binding("L", "load_all", "All rows", show=False, id="grid.load_all"),
        Binding("e", "export", "Export", id="grid.export"),
    ]

    class Summary(Message):
        def __init__(self, text: str) -> None:
            super().__init__()
            self.text = text

    class FilterRequested(Message):
        pass

    class ExportRequested(Message):
        def __init__(self, grid: ResultGrid) -> None:
            super().__init__()
            self.grid = grid

    def __init__(
        self,
        columns: Sequence[Column],
        rows: Sequence[tuple[Any, ...]] = (),
        source: RowSource | None = None,
        page_size: int = 500,
        sql: str = "",
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self.sql = sql  # the statement that produced this result (for re-run exports)
        self.model = GridModel(columns, rows)
        self.source = source
        self.page_size = page_size
        self._loading = False
        self._widths: list[int] = []
        self._starts: list[int] = []
        self._gw = 4
        self._anchor = (0, 0)
        self._cursor = (0, 0)
        self._dragging = False

    # --- state ---
    @property
    def cursor(self) -> tuple[int, int]:
        return self._cursor

    @property
    def summary_text(self) -> str:
        m = self.model
        text = f"{m.total_rows} rows"
        if m.filter_text:
            text = f"{len(m)} of {m.total_rows} rows (filtered)"
        if self.source is not None:
            text += " (more…)"
        return text

    def on_mount(self) -> None:
        self._relayout()

    # --- layout ---
    def _relayout(self) -> None:
        m = self.model
        sample = m.rows(0, min(len(m), SAMPLE_ROWS) - 1)
        widths = []
        for ci, col in enumerate(m.columns):
            w = max(
                [len(col.name) + 3, *(len(format_value(r[ci])) for r in sample)], default=MIN_COL
            )
            widths.append(max(MIN_COL, min(MAX_COL, w)))
        self._widths = widths
        self._starts = [0]
        for w in widths:
            self._starts.append(self._starts[-1] + w + 1)  # +1 separator
        self._gw = max(4, len(str(max(m.total_rows, 1))) + 2)
        self.virtual_size = Size(self._gw + self._starts[-1], len(m) + 1)
        self.refresh()

    # --- drawing ---
    def render_line(self, y: int) -> Strip:
        width = self.size.width
        scroll_x, scroll_y = self.scroll_offset
        gw = self._gw
        st = self._styles()
        if y == 0:
            gutter = Segment(" " * gw, st["header"])
            data = self._header_segments(st)
        else:
            vr = y - 1 + scroll_y
            if vr >= len(self.model):
                if vr == 0:
                    return Strip([Segment("  (no rows)", st["null"])]).extend_cell_length(width)
                return Strip.blank(width, self.rich_style)
            gutter = Segment(str(vr + 1).rjust(gw - 1) + " ", st["gutter"])
            data = self._row_segments(vr, st)
        body = Strip(data).crop(scroll_x, scroll_x + max(0, width - gw))
        return Strip.join([Strip([gutter]), body]).extend_cell_length(width, self.rich_style)

    def _styles(self) -> dict[str, Style]:
        g = self.get_component_rich_style
        base = self.rich_style
        return {
            "base": base,
            "header": base + g("result-grid--header"),
            "gutter": base + g("result-grid--gutter"),
            "cursor": base + g("result-grid--cursor"),
            "selection": base + g("result-grid--selection"),
            "stripe": base + g("result-grid--stripe"),
            "null": base + g("result-grid--null"),
            "sep": base + g("result-grid--sep"),
        }

    def _header_segments(self, st: dict[str, Style]) -> list[Segment]:
        segs: list[Segment] = []
        multi = len(self.model.sort) > 1
        for ci, col in enumerate(self.model.columns):
            label = col.name
            if state := self.model.sort_state(ci):
                desc, rank = state
                label += (" ▼" if desc else " ▲") + (str(rank) if multi else "")
            segs.append(Segment(_fit(label, self._widths[ci], False), st["header"]))
            segs.append(Segment("│", st["header"]))
        return segs

    def _row_segments(self, vr: int, st: dict[str, Style]) -> list[Segment]:
        segs: list[Segment] = []
        r0, c0, r1, c1 = self.selection_rect()
        row = self.model.row(vr)
        base = st["stripe"] if vr % 2 else st["base"]
        for ci, value in enumerate(row):
            text = format_value(value)
            style = st["null"] if value is None and text == NULL_TEXT else base
            if r0 <= vr <= r1 and c0 <= ci <= c1:
                style = st["selection"]
            if (vr, ci) == self._cursor:
                style = st["cursor"]
            right = isinstance(value, _NUMERIC) and not isinstance(value, bool)
            segs.append(Segment(_fit(text, self._widths[ci], right), style))
            segs.append(Segment("│", st["sep"] if vr % 2 == 0 else st["sep"] + st["stripe"]))
        return segs

    # --- selection ---
    def selection_rect(self) -> tuple[int, int, int, int]:
        (ar, ac), (cr, cc) = self._anchor, self._cursor
        return min(ar, cr), min(ac, cc), max(ar, cr), max(ac, cc)

    def _set_cursor(self, row: int, col: int, extend: bool = False) -> None:
        n_rows, n_cols = len(self.model), len(self.model.columns)
        if n_rows == 0 or n_cols == 0:
            return
        self._cursor = (max(0, min(row, n_rows - 1)), max(0, min(col, n_cols - 1)))
        if not extend:
            self._anchor = self._cursor
        self._ensure_visible()
        self.refresh()
        self._maybe_load_more()

    def _ensure_visible(self) -> None:
        row, col = self._cursor
        h = max(1, self.size.height - 1)
        x, y = self.scroll_offset
        if row < y:
            y = row
        elif row >= y + h:
            y = row - h + 1
        data_w = max(1, self.size.width - self._gw)
        left, right = self._starts[col], self._starts[col + 1]
        if left < x:
            x = left
        elif right > x + data_w:
            x = min(right - data_w, left)
        self.scroll_to(x=x, y=y, animate=False)

    def action_move(self, dr: int, dc: int, extend: bool = False) -> None:
        self._set_cursor(self._cursor[0] + dr, self._cursor[1] + dc, extend)

    def action_page(self, direction: int) -> None:
        self._set_cursor(
            self._cursor[0] + direction * max(1, self.size.height - 2), self._cursor[1]
        )

    def action_row_edge(self, end: int) -> None:
        self._set_cursor(self._cursor[0], len(self.model.columns) - 1 if end else 0)

    def action_grid_edge(self, end: int) -> None:
        """Ctrl+Home / Ctrl+End: top-left / bottom-right cell."""
        if end:
            self._set_cursor(len(self.model) - 1, len(self.model.columns) - 1)
        else:
            self._set_cursor(0, 0)

    def action_select_all(self) -> None:
        n, c = len(self.model), len(self.model.columns)
        if n and c:
            self._anchor, self._cursor = (0, 0), (n - 1, c - 1)
            self.refresh()

    # --- mouse ---
    def _hit(self, x: int, y: int) -> tuple[int, int] | None:
        """(view_row, col) under a viewport point; row -1 = header, col -1 = row gutter."""
        sx, sy = self.scroll_offset
        col = -1
        if x >= self._gw:
            col = bisect.bisect_right(self._starts, x - self._gw + sx) - 1
            if not 0 <= col < len(self.model.columns):
                return None
        row = -1 if y == 0 else y - 1 + sy
        return (row, col) if row < len(self.model) else None

    def on_mouse_down(self, event: events.MouseDown) -> None:
        hit = self._hit(event.x, event.y)
        self.focus()
        if hit is None:
            return
        row, col = hit
        if row == -1:
            if col >= 0:
                self._sort(col, add=event.shift)
            return
        if col == -1:  # row number: select the whole row
            self._anchor, self._cursor = (row, 0), (row, len(self.model.columns) - 1)
            self.refresh()
            return
        self._set_cursor(row, col, extend=event.shift)
        self._dragging = True
        self.capture_mouse()

    def on_mouse_move(self, event: events.MouseMove) -> None:
        if self._dragging and (hit := self._hit(event.x, event.y)):
            row, col = hit
            if row >= 0 and col >= 0:
                self._set_cursor(row, col, extend=True)

    def on_mouse_up(self, _: events.MouseUp) -> None:
        if self._dragging:
            self._dragging = False
            self.release_mouse()

    # --- sort / filter ---
    def _sort(self, col: int, add: bool = False) -> None:
        self.model.cycle_sort(col, add)
        self._anchor = self._cursor = (
            min(self._cursor[0], max(0, len(self.model) - 1)),
            self._cursor[1],
        )
        self.refresh()

    def action_sort(self, add: bool = False) -> None:
        self._sort(self._cursor[1], add)

    def action_filter(self) -> None:
        self.post_message(self.FilterRequested())

    def set_filter(self, text: str) -> None:
        self.model.set_filter(text)
        self._anchor = self._cursor = (0, self._cursor[1])
        self.scroll_to(0, 0, animate=False)
        self._relayout()
        self.post_message(self.Summary(self.summary_text))

    # --- paging ---
    def _maybe_load_more(self) -> None:
        if (
            self.source is not None
            and not self._loading
            and self._cursor[0] >= len(self.model) - LOAD_AHEAD
        ):
            self.action_load_more()

    def action_load_more(self) -> None:
        if self.source is not None and not self._loading:
            self._loading = True
            self.run_worker(self._fetch(False), group="grid-fetch", exit_on_error=False)

    def action_load_all(self) -> None:
        if self.source is not None and not self._loading:
            self._loading = True
            self.run_worker(self._fetch(True), group="grid-fetch", exit_on_error=False)

    async def _fetch(self, everything: bool) -> None:
        try:
            while self.source is not None:
                rows, done = await self.source.fetch_more(self.page_size)
                self.model.append(rows)
                if done:
                    self.source = None
                self._relayout()
                self.post_message(self.Summary(self.summary_text))
                if not everything:
                    break
        except DbError as e:
            self.source = None
            self.app.notify(str(e), title="Cannot load more rows", severity="error")
            self.post_message(self.Summary(self.summary_text))
        finally:
            self._loading = False

    # --- copy / view ---
    def selection_data(self) -> tuple[list[Column], list[tuple[Any, ...]]]:
        """Columns and rows of the selection rectangle (view order)."""
        r0, c0, r1, c1 = self.selection_rect()
        rows = [row[c0 : c1 + 1] for row in self.model.rows(r0, r1)]
        return self.model.columns[c0 : c1 + 1], rows

    def _selected(self) -> tuple[list[tuple[Any, ...]], list[str]]:
        cols, rows = self.selection_data()
        return rows, [c.name for c in cols]

    def render_copy(self, fmt: str) -> str:
        rows, head = self._selected()
        match fmt:
            case "tsv":
                return copyfmt.to_tsv(rows)
            case "tsv_header":
                return copyfmt.to_tsv(rows, head)
            case "csv":
                return copyfmt.to_csv(rows, head)
            case "markdown":
                return copyfmt.to_markdown(rows, head)
            case "json":
                return copyfmt.to_json(rows, head)
            case "insert":
                return copyfmt.to_insert_sql(rows, head)
            case "cell":
                return raw_text(self.model.value(*self._cursor))
        raise ValueError(f"unknown copy format {fmt}")

    def copy(self, fmt: str = "tsv") -> None:
        if not len(self.model):
            return
        text = self.render_copy(fmt)
        used = clipboard.copy_native(text)
        if used is None:
            self.app.copy_to_clipboard(text)
        rows, head = self._selected()
        self.app.notify(f"Copied {len(rows)}×{len(head)} ({used or 'terminal clipboard'})")

    def action_export(self) -> None:
        if len(self.model):
            self.post_message(self.ExportRequested(self))

    def action_copy(self) -> None:
        self.copy("tsv")

    def action_copy_menu(self) -> None:
        if len(self.model):
            self.app.push_screen(CopyMenu(), lambda fmt: self.copy(fmt) if fmt else None)

    def action_view_value(self) -> None:
        if not len(self.model):
            return
        row, col = self._cursor
        column = self.model.columns[col]
        value = self.model.value(row, col)
        self.app.push_screen(
            ValueViewer(
                describe_cell(column.name, column.type_name, value), raw_text(value) or NULL_TEXT
            )
        )


def _fit(text: str, width: int, right: bool) -> str:
    if len(text) > width:
        text = text[: width - 1] + "…"
    return text.rjust(width) if right else text.ljust(width)
