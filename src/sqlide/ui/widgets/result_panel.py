"""Tabs under the editor: an Output log plus one tab per result set."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import RichLog, Static, TabbedContent, TabPane

from sqlide.db.result import Column, RowSource
from sqlide.history.results import SavedResult
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.result_view import ResultView
from sqlide.ui.widgets.toolbar import RESULT_TOOLS, IconButton

OUTPUT = "output"
MAX_PINNED = 20
PIN = "📌 "


class ResultBar(Horizontal):
    """One-line buttons for the active result tab: pin, close, copy, export, re-run."""

    DEFAULT_CSS = """
    ResultBar { height: 1; dock: top; background: $boost; }
    ResultBar .spacer { width: 1fr; }
    """

    def __init__(self, ascii_icons: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self.ascii_icons = ascii_icons

    def compose(self) -> ComposeResult:
        yield Static("", classes="spacer")
        for tool in RESULT_TOOLS:
            yield IconButton(tool, self.ascii_icons)

    def refresh_tips(self) -> None:
        for button in self.query(IconButton):
            button.refresh_tip()

    def sync(self, has_result: bool, pinned: bool) -> None:
        for button in self.query(IconButton):
            button.set_class(not has_result, "-off")
            if button.tool.key_id == "grid.pin":
                button.update("📍" if pinned and not self.ascii_icons else button.tool.icon)


class ResultPanel(Vertical):
    def __init__(self, ascii_icons: bool = False, **kw: Any) -> None:
        super().__init__(**kw)
        self._counter = 0
        self._ascii = ascii_icons
        self._pinned: set[str] = set()
        self._titles: dict[str, str] = {}
        self._stamps: dict[str, float] = {}

    def compose(self) -> ComposeResult:
        yield ResultBar(self._ascii, id="result-bar")
        with TabbedContent(id="tabs"), TabPane("Output", id=OUTPUT):
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)

    @property
    def tabs(self) -> TabbedContent:
        return self.query_one("#tabs", TabbedContent)

    @property
    def bar(self) -> ResultBar:
        return self.query_one("#result-bar", ResultBar)

    def log_line(self, text: str, style: str = "") -> None:
        self.query_one("#log", RichLog).write(Text(text, style=style))

    def log_error(self, text: str) -> None:
        self.log_line(text, "bold red")

    def clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    @property
    def result_pane_ids(self) -> list[str]:
        return [p.id for p in self.tabs.query(TabPane) if p.id and p.id != OUTPUT]

    @property
    def pinned_ids(self) -> list[str]:
        return [i for i in self.result_pane_ids if i in self._pinned]

    @property
    def active_result_id(self) -> str | None:
        active = self.tabs.active
        return active if active and active != OUTPUT and active in self.result_pane_ids else None

    def is_pinned(self, pane_id: str) -> bool:
        return pane_id in self._pinned

    def pane_id_of(self, grid: ResultGrid) -> str | None:
        pane = next((a for a in grid.ancestors if isinstance(a, TabPane)), None)
        return pane.id if pane is not None else None

    def grid_of(self, pane_id: str) -> ResultGrid | None:
        grids = self.tabs.get_pane(pane_id).query(ResultGrid)
        return grids.first() if grids else None

    async def reset_results(self) -> None:
        """A new run starts: drop the tabs of earlier runs, keep the pinned ones."""
        for pane_id in self.result_pane_ids:
            if pane_id not in self._pinned:
                await self._remove(pane_id)
        self.tabs.active = OUTPUT

    async def _remove(self, pane_id: str) -> None:
        self._pinned.discard(pane_id)
        self._titles.pop(pane_id, None)
        self._stamps.pop(pane_id, None)
        await self.tabs.remove_pane(pane_id)

    async def close_result(self, pane_id: str) -> None:
        await self._remove(pane_id)
        rest = self.result_pane_ids
        self.tabs.active = rest[-1] if rest else OUTPUT

    def _relabel(self, pane_id: str) -> None:
        title = self._titles.get(pane_id, "")
        self.tabs.get_tab(pane_id).label = Text((PIN if pane_id in self._pinned else "") + title)

    def toggle_pin(self, pane_id: str) -> bool | None:
        """Pin/unpin a result tab. None when refused (too many pinned)."""
        if pane_id in self._pinned:
            self._pinned.discard(pane_id)
        elif len(self._pinned) >= MAX_PINNED:
            return None
        else:
            self._pinned.add(pane_id)
        self._relabel(pane_id)
        return pane_id in self._pinned

    async def add_result(
        self,
        title: str,
        columns: Sequence[Column],
        rows: Sequence[tuple[Any, ...]],
        source: RowSource | None = None,
        page_size: int = 500,
        sql: str = "",
        *,
        pinned: bool = False,
        stamp: float | None = None,
    ) -> ResultGrid:
        self._counter += 1
        pane_id = f"r{self._counter}"
        grid = ResultGrid(columns, rows, source, page_size, sql)
        self._titles[pane_id] = title
        self._stamps[pane_id] = time.time() if stamp is None else stamp
        if pinned:
            self._pinned.add(pane_id)
        label = (PIN if pinned else "") + title
        pane = TabPane(label, ResultView(grid), id=pane_id)
        pane.tooltip = sql.strip()[:400] or None
        await self.tabs.add_pane(pane)
        return grid

    def show_first_result(self) -> None:
        """After a run: show the first new result (else the first pinned one)."""
        ids = self.result_pane_ids
        fresh = [i for i in ids if i not in self._pinned]
        if fresh or ids:
            self.tabs.active = (fresh or ids)[0]

    def snapshots(self) -> list[SavedResult]:
        """Every result tab as plain data, for saving between sessions."""
        out = []
        for pane_id in self.result_pane_ids:
            grid = self.grid_of(pane_id)
            if grid is None:
                continue
            out.append(
                SavedResult(
                    self._titles.get(pane_id, ""),
                    grid.sql,
                    self._stamps.get(pane_id, 0.0),
                    pane_id in self._pinned,
                    list(grid.model.columns),
                    grid.model.loaded_rows(),
                    grid.source is not None,
                )
            )
        return out

    def focus_active(self) -> None:
        """Put the keyboard on the visible result grid (or the tab strip for the log)."""
        grids = self.tabs.get_pane(self.tabs.active).query(ResultGrid)
        (grids.first() if grids else self.tabs).focus()

    def sync_bar(self) -> None:
        active = self.active_result_id
        self.bar.sync(active is not None, active is not None and active in self._pinned)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self.sync_bar()
