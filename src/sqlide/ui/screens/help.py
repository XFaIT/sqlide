"""F1: every action with its key, plus the few keys that are not rebindable actions."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, RichLog

EXTRA = (
    ("Schema tree: choose schemas / databases", "S"),
    ("Schema tree: re-read from the database", "F5"),
    ("Schema tree: insert name into the editor", "I"),
    ("Command palette (every action by name)", "Ctrl+P"),
    ("Quit", "Ctrl+Q"),
)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [Binding("escape,f1,q", "close", "Close")]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Label(
                "Keys (Esc closes; rebind in keymap.toml, `sqlide keys` lists ids)", id="help-title"
            )
            yield RichLog(id="help-log", markup=False, wrap=False)

    def on_mount(self) -> None:
        from sqlide.ui.keymap import catalogue  # late: keymap imports the screens

        log = self.query_one("#help-log", RichLog)
        rows = [(i.description, i.keys.replace(",", "  /  ")) for i in catalogue() if i.description]
        rows += list(EXTRA)
        width = max(len(d) for d, _ in rows)
        for desc, keys in rows:
            log.write(f"{desc:<{width}}  {keys}")
        log.focus()

    def action_close(self) -> None:
        self.dismiss(None)
