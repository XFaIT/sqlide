"""Settings form. Returns a new Settings (or None when cancelled)."""

from __future__ import annotations

from dataclasses import replace

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Switch

from sqlide.config.settings import Settings


class SettingsScreen(ModalScreen[Settings | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, settings: Settings, themes: list[str]) -> None:
        super().__init__()
        self._settings = settings
        self._themes = themes

    def compose(self) -> ComposeResult:
        s = self._settings
        with Vertical(classes="dialog", id="settings"):
            yield Label("Settings", classes="title")
            yield Label("Theme")
            yield Select(
                [(t, t) for t in self._themes],
                value=s.theme if s.theme in self._themes else Select.BLANK,
                allow_blank=False,
                id="theme",
            )
            yield Label("Rows per page")
            yield Input(str(s.fetch_size), type="integer", id="fetch")
            yield Label("History entries to keep")
            yield Input(str(s.history_limit), type="integer", id="keep")
            with Horizontal(classes="row"):
                yield Switch(s.split_on_blank_line, id="blank")
                yield Label(" A blank line ends a statement")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")
            yield Label("", id="settings-error", classes="error")

    def _collect(self) -> Settings | str:
        try:
            fetch = int(self.query_one("#fetch", Input).value)
            keep = int(self.query_one("#keep", Input).value)
        except ValueError:
            return "Numbers only"
        if not 1 <= fetch <= 100_000:
            return "Rows per page: 1 – 100000"
        if not 10 <= keep <= 1_000_000:
            return "History entries: 10 – 1000000"
        theme = self.query_one("#theme", Select).value
        return replace(
            self._settings,
            theme=str(theme) if isinstance(theme, str) else self._settings.theme,
            fetch_size=fetch,
            history_limit=keep,
            split_on_blank_line=self.query_one("#blank", Switch).value,
        )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "save":
            self.dismiss(None)
            return
        result = self._collect()
        if isinstance(result, str):
            self.query_one("#settings-error", Label).update(result)
        else:
            self.dismiss(result)

    def action_cancel(self) -> None:
        self.dismiss(None)
