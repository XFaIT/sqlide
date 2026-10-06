"""Small reusable modals: confirm, password prompt, progress."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, ProgressBar


class ConfirmScreen(ModalScreen[bool]):
    BINDINGS = [Binding("escape", "no", "No"), Binding("y", "yes", "Yes"), Binding("n", "no", "No")]

    def __init__(self, message: str, yes: str = "Yes", no: str = "No") -> None:
        super().__init__()
        self._message, self._yes, self._no = message, yes, no

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._message)
            with Horizontal(classes="buttons"):
                yield Button(self._yes, variant="primary", id="yes")
                yield Button(self._no, id="no")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_yes(self) -> None:
        self.dismiss(True)

    def action_no(self) -> None:
        self.dismiss(False)


class PasswordPrompt(ModalScreen[str | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title)
            yield Input(password=True, id="pw", placeholder="password")
            with Horizontal(classes="buttons"):
                yield Button("Connect", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#pw", Input).focus()

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.dismiss(self.query_one("#pw", Input).value)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self.query_one("#pw", Input).value if event.button.id == "ok" else None)

    def action_cancel(self) -> None:
        self.dismiss(None)


class ProgressScreen(ModalScreen[None]):
    """Shown while a download runs; the caller dismisses it."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self._title = title

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Label(self._title)
            yield ProgressBar(total=None, show_eta=False, id="bar")

    def advance(self, done: int, total: int | None) -> None:
        self.query_one("#bar", ProgressBar).update(total=total, progress=done)


class PathPrompt(ModalScreen[str | None]):
    """Ask for a file path (open / save as)."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, title: str, default: str = "", ok: str = "OK") -> None:
        super().__init__()
        self._title, self._default, self._ok = title, default, ok

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label(self._title)
            yield Input(self._default, id="path")
            with Horizontal(classes="buttons"):
                yield Button(self._ok, variant="primary", id="ok")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        self.query_one("#path", Input).focus()

    def _value(self) -> str | None:
        return self.query_one("#path", Input).value.strip() or None

    def on_input_submitted(self, _: Input.Submitted) -> None:
        self.dismiss(self._value())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(self._value() if event.button.id == "ok" else None)

    def action_cancel(self) -> None:
        self.dismiss(None)
