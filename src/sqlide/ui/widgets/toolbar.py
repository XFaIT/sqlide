"""Icon toolbar: one-line row of buttons; hovering shows the name, the key and what it does.

Tooltips are built from the effective keymap, so a rebound key shows up at once.
"""

from __future__ import annotations

from dataclasses import dataclass

from textual import events
from textual.containers import Horizontal
from textual.widgets import Static


@dataclass(frozen=True, slots=True)
class Tool:
    icon: str
    ascii: str
    title: str
    about: str
    action: str  # Textual action string run on the main screen
    key_id: str  # keymap id whose key is shown ("" = none)
    needs: str = ""  # "" always on | "running" | "manual_tx" | "session"


TOOLS: tuple[Tool, ...] = (
    Tool(
        "▶",
        "Run",
        "Run",
        "Run the statement under the cursor (or the selection)",
        "console('run_statement')",
        "editor.run",
    ),
    Tool(
        "▶▶",
        "All",
        "Run all",
        "Run every statement in the editor, one after another",
        "console('run_all')",
        "editor.run_all",
    ),
    Tool(
        "■",
        "Stop",
        "Cancel",
        "Cancel the running query",
        "console('cancel')",
        "console.cancel",
        "running",
    ),
    Tool(
        "⇄",
        "Tx",
        "Auto / Manual commit",
        "Switch between auto-commit and manual transactions",
        "console('toggle_tx')",
        "console.toggle_tx",
        "session",
    ),
    Tool(
        "✓",
        "Ok",
        "Commit",
        "Commit the open transaction (manual mode)",
        "console('commit')",
        "console.commit",
        "manual_tx",
    ),
    Tool(
        "↶",
        "Undo",
        "Rollback",
        "Roll back the open transaction (manual mode)",
        "console('rollback')",
        "console.rollback",
        "manual_tx",
    ),
    Tool(
        "¶",
        "Fmt",
        "Format SQL",
        "Re-format the selection, or the statement under the cursor",
        "console('format')",
        "editor.format",
    ),
    Tool(
        "◷", "Hist", "History", "Search the history of executed queries", "history", "main.history"
    ),
    Tool(
        "+",
        "+Con",
        "New connection",
        "Add a database connection",
        "new_connection",
        "main.new_connection",
    ),
    Tool(
        "⊞",
        "+Tab",
        "New console",
        "Open another SQL console tab",
        "new_console",
        "main.new_console",
    ),
    Tool("▤", "Open", "Open file", "Open a .sql file in a new tab", "open_file", "main.open_file"),
    Tool("▣", "Save", "Save", "Save the current tab to a file", "save_file", "main.save_file"),
    Tool("?", "Help", "Keys and help", "All keys; Enter on a row changes it", "help", "main.help"),
)


class IconButton(Static):
    DEFAULT_CSS = """
    IconButton { width: auto; min-width: 3; height: 1; padding: 0 1; content-align: center middle; }
    IconButton:hover { background: $primary; color: $text; }
    IconButton.-off { color: $text-disabled; }
    IconButton.-off:hover { background: transparent; }
    """

    def __init__(self, tool: Tool, ascii_icons: bool) -> None:
        super().__init__(tool.ascii if ascii_icons else tool.icon, markup=False)
        self.tool = tool
        self.refresh_tip()

    def refresh_tip(self) -> None:
        from sqlide.ui.keymap import keys_for  # late: keymap imports the app

        t = self.tool
        key = keys_for(t.key_id, limit=0) if t.key_id else ""
        head = f"{t.title} ({key})" if key else t.title
        self.tooltip = f"{head}\n{t.about}"

    async def on_click(self, event: events.Click) -> None:
        event.stop()
        if not self.has_class("-off"):
            await self.screen.run_action(self.tool.action)


class Toolbar(Horizontal):
    DEFAULT_CSS = """
    Toolbar { height: 1; background: $panel; }
    Toolbar .brand { width: auto; padding: 0 1; text-style: bold; color: $accent; }
    """

    def __init__(self, ascii_icons: bool = False, **kw) -> None:
        super().__init__(**kw)
        self.ascii_icons = ascii_icons

    def compose(self):
        yield Static("sqlide", classes="brand", markup=False)
        for tool in TOOLS:
            yield IconButton(tool, self.ascii_icons)

    def refresh_tips(self) -> None:
        for button in self.query(IconButton):
            button.refresh_tip()

    def sync(self, console) -> None:
        """Dim the buttons that cannot do anything right now."""
        session = getattr(console, "session", None)
        state = {
            "running": bool(console and console.running),
            "session": session is not None,
            "manual_tx": session is not None and not session.autocommit,
        }
        for button in self.query(IconButton):
            need = button.tool.needs
            button.set_class(bool(need) and not state[need], "-off")
