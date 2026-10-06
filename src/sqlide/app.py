"""Textual application: only wires the workspace to the main screen."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from sqlide.ui.screens.main import MainScreen
from sqlide.workspace import Workspace


class SqlideApp(App):
    CSS_PATH = str(Path(__file__).parent / "ui" / "app.tcss")
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True)]

    def __init__(self, workspace: Workspace | None = None) -> None:
        super().__init__()
        self.workspace = workspace or Workspace()

    def on_mount(self) -> None:
        self.main = MainScreen(self.workspace)
        self.push_screen(self.main)

    async def action_quit(self) -> None:
        await self.main.console.detach()  # cancel a running query, close the connection
        self.exit()
