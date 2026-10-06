"""The completion list shown under the editor cursor."""

from __future__ import annotations

from rich.text import Text
from textual.geometry import Offset
from textual.widgets import OptionList
from textual.widgets.option_list import Option

from sqlide.db.completion import Candidate

ICONS = {
    "column": "▪",
    "table": "▤",
    "view": "◫",
    "schema": "▣",
    "keyword": "·",
    "function": "ƒ",
}
MAX_ROWS = 10


def _prompt(c: Candidate) -> Text:
    t = Text(f"{ICONS.get(c.kind, ' ')} {c.text}")
    if c.detail:
        t.append(f"  {c.detail}", style="dim")
    return t


class CompletionPopup(OptionList):
    """Pure view: the editor decides when to show it and what accepting means."""

    DEFAULT_CSS = """
    CompletionPopup {
        overlay: screen;
        position: absolute;
        display: none;
        width: 44;
        height: auto;
        max-height: 12;
        border: round $primary;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__(compact=True)
        self.can_focus = False  # the editor keeps focus; it forwards the navigation keys
        self._items: list[Candidate] = []

    @property
    def shown(self) -> bool:
        return bool(self.display)

    def show(self, items: list[Candidate], at: Offset) -> None:
        self._items = items
        self.clear_options()
        self.add_options([Option(_prompt(c)) for c in items])
        self.highlighted = 0
        rows = min(len(items), MAX_ROWS) + 2
        self.styles.height = rows
        screen = self.screen.size
        x = max(0, min(at.x, screen.width - 46))
        y = at.y + 1
        if y + rows + 1 > screen.height:  # no room below: open upwards
            y = max(0, at.y - rows - 1)
        self.styles.offset = (x, y)
        self.display = True

    def hide(self) -> None:
        self.display = False
        self._items = []

    def move(self, step: int) -> None:
        if self._items:
            self.highlighted = ((self.highlighted or 0) + step) % len(self._items)

    @property
    def current(self) -> Candidate | None:
        i = self.highlighted
        return self._items[i] if i is not None and 0 <= i < len(self._items) else None
