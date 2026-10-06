"""Query history browser: search, preview, insert into the editor or run again."""

from __future__ import annotations

from datetime import datetime

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from sqlide.history import HistoryEntry, HistoryStore


class HistoryChoice:
    """What the user picked: the statement, and whether to run it right away."""

    __slots__ = ("run", "sql")

    def __init__(self, sql: str, run: bool) -> None:
        self.sql, self.run = sql, run


def _line(e: HistoryEntry) -> Text:
    when = datetime.fromtimestamp(e.ts).strftime("%m-%d %H:%M")
    t = Text(f"{when}  ")
    t.append("✔ " if e.ok else "✖ ", style="green" if e.ok else "red")
    t.append(f"[{e.connection}] ", style="cyan")
    t.append(" ".join(e.sql.split())[:200])
    return t


class HistoryScreen(ModalScreen[HistoryChoice | None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("down", "move(1)", show=False),
        Binding("up", "move(-1)", show=False),
        Binding("pagedown", "move(10)", show=False),
        Binding("pageup", "move(-10)", show=False),
        Binding("enter", "insert", "Insert"),
        Binding("f5,ctrl+j", "run", "Run"),
        Binding("alt+c", "toggle_scope", "This connection only"),
        Binding("alt+d", "delete", "Delete entry"),
    ]

    def __init__(self, store: HistoryStore, connection: str = "") -> None:
        super().__init__()
        self._store = store
        self._connection = connection
        self._only_current = False
        self._entries: list[HistoryEntry] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="history"):
            yield Label(id="history-title")
            yield Input(placeholder="type to filter (all words must match)", id="history-filter")
            yield OptionList(id="history-list")
            yield Static(id="history-preview")

    def on_mount(self) -> None:
        self.query_one("#history-filter", Input).focus()
        self._reload()

    # --- data ---
    def _reload(self) -> None:
        text = self.query_one("#history-filter", Input).value
        scope = self._connection if self._only_current and self._connection else None
        self._entries = self._store.search(text, connection=scope)
        lst = self.query_one("#history-list", OptionList)
        lst.clear_options()
        lst.add_options([Option(_line(e)) for e in self._entries])
        if self._entries:
            lst.highlighted = 0
        title = "History" + (f" · {self._connection} only" if scope else " · all connections")
        self.query_one("#history-title", Label).update(f"{title} · {len(self._entries)} entries")
        self._preview()

    def _current(self) -> HistoryEntry | None:
        i = self.query_one("#history-list", OptionList).highlighted
        return self._entries[i] if i is not None and 0 <= i < len(self._entries) else None

    def _preview(self) -> None:
        e = self._current()
        text = "" if e is None else e.sql + (f"\n\n-- {e.error}" if e.error else "")
        self.query_one("#history-preview", Static).update(Text(text))

    # --- events ---
    def on_input_changed(self, _: Input.Changed) -> None:
        self._reload()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.action_insert()

    def on_option_list_option_highlighted(self, _: OptionList.OptionHighlighted) -> None:
        self._preview()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_insert()

    # --- actions ---
    def action_move(self, step: int) -> None:
        lst = self.query_one("#history-list", OptionList)
        if self._entries:
            current = lst.highlighted or 0
            lst.highlighted = max(0, min(len(self._entries) - 1, current + step))

    def action_insert(self) -> None:
        if e := self._current():
            self.dismiss(HistoryChoice(e.sql, run=False))

    def action_run(self) -> None:
        if e := self._current():
            self.dismiss(HistoryChoice(e.sql, run=True))

    def action_toggle_scope(self) -> None:
        self._only_current = not self._only_current
        self._reload()

    def action_delete(self) -> None:
        if e := self._current():
            self._store.delete(e.id)
            self._reload()

    def action_close(self) -> None:
        self.dismiss(None)
