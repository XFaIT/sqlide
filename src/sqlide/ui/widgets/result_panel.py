"""Tabs under the editor: an Output log plus one tab per result set."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import RichLog, TabbedContent, TabPane

from sqlide.db.result import Column, RowSource
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.result_view import ResultView

OUTPUT = "output"


class ResultPanel(Vertical):
    def __init__(self, **kw: Any) -> None:
        super().__init__(**kw)
        self._counter = 0

    def compose(self) -> ComposeResult:
        with TabbedContent(id="tabs"), TabPane("Output", id=OUTPUT):
            yield RichLog(id="log", wrap=True, markup=False, highlight=False)

    @property
    def tabs(self) -> TabbedContent:
        return self.query_one("#tabs", TabbedContent)

    def log_line(self, text: str, style: str = "") -> None:
        self.query_one("#log", RichLog).write(Text(text, style=style))

    def log_error(self, text: str) -> None:
        self.log_line(text, "bold red")

    def clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    @property
    def result_pane_ids(self) -> list[str]:
        return [p.id for p in self.tabs.query(TabPane) if p.id and p.id != OUTPUT]

    async def reset_results(self) -> None:
        for pane_id in self.result_pane_ids:
            await self.tabs.remove_pane(pane_id)
        self.tabs.active = OUTPUT

    async def add_result(
        self,
        title: str,
        columns: Sequence[Column],
        rows: Sequence[tuple[Any, ...]],
        source: RowSource | None = None,
        page_size: int = 500,
    ) -> ResultGrid:
        self._counter += 1
        grid = ResultGrid(columns, rows, source, page_size)
        await self.tabs.add_pane(TabPane(title, ResultView(grid), id=f"r{self._counter}"))
        return grid

    def show_first_result(self) -> None:
        ids = self.result_pane_ids
        if ids:
            self.tabs.active = ids[0]
