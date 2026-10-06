"""One result tab: optional filter bar above the grid."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Input

from sqlide.ui.widgets.result_grid import ResultGrid


class ResultView(Vertical):
    DEFAULT_CSS = """
    ResultView { height: 1fr; }
    ResultView > Input { height: 3; display: none; }
    """

    def __init__(self, grid: ResultGrid, **kw) -> None:
        super().__init__(**kw)
        self.grid = grid

    def compose(self) -> ComposeResult:
        yield Input(placeholder="filter rows… (Esc closes)", id="filter")
        yield self.grid

    @property
    def filter_input(self) -> Input:
        return self.query_one("#filter", Input)

    def on_result_grid_filter_requested(self, _: ResultGrid.FilterRequested) -> None:
        bar = self.filter_input
        bar.display = True
        bar.value = self.grid.model.filter_text
        bar.focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        self.grid.set_filter(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.grid.focus()  # keep the filter active, return to the table

    def on_key(self, event: events.Key) -> None:
        if event.key == "escape" and self.filter_input.has_focus:
            event.stop()
            self.filter_input.value = ""
            self.filter_input.display = False
            self.grid.focus()
