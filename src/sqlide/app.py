"""Textual application: only wires the workspace to the main screen."""

from __future__ import annotations

from pathlib import Path

from textual.app import App
from textual.binding import Binding

from sqlide.config.keymap import load_keymap
from sqlide.ui.screens.main import MainScreen
from sqlide.workspace import Workspace


class SqlideApp(App):
    CSS_PATH = str(Path(__file__).parent / "ui" / "app.tcss")
    BINDINGS = [Binding("ctrl+q", "quit", "Quit", priority=True, id="app.quit")]

    def __init__(self, workspace: Workspace | None = None, files: list[Path] | None = None) -> None:
        super().__init__()
        self.workspace = workspace or Workspace()
        self._files = files or []

    def on_mount(self) -> None:
        self.set_keymap(load_keymap())  # user overrides from keymap.toml
        self.main = MainScreen(self.workspace, self._files)
        self.push_screen(self.main)

    async def action_quit(self) -> None:
        await self.main.tabs.shutdown()  # save consoles, cancel queries, close connections
        self.exit()
