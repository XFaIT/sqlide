"""F1: every action with its current key. Enter on a row rebinds it; Backspace resets it."""

from __future__ import annotations

from textual import events
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList
from textual.widgets.option_list import Option

from sqlide.config.keymap import load_keymap, save_override

EXTRA = (("Command palette (every action by name)", "Ctrl+P"),)

_MODIFIER_KEYS = {"shift", "ctrl", "alt", "super", "meta", "hyper", "caps_lock"}


class RebindScreen(ModalScreen[str | None]):
    """Waits for one key press; Esc cancels. Returns the Textual key name."""

    def __init__(self, description: str, current: str) -> None:
        super().__init__()
        self.description = description
        self.current = current

    def compose(self) -> ComposeResult:
        with Vertical(id="rebind-box"):
            yield Label(f"Press the new key for “{self.description}”", id="rebind-title")
            yield Label(f"now: {self.current}    Esc cancels", id="rebind-hint")

    def on_key(self, event: events.Key) -> None:
        event.stop()
        event.prevent_default()
        if event.key == "escape":
            self.dismiss(None)
        elif event.key not in _MODIFIER_KEYS:
            self.dismiss(event.key)


class HelpScreen(ModalScreen[None]):
    BINDINGS = [
        Binding("escape,f1,q", "close", "Close"),
        Binding("backspace,delete", "reset", "Reset key"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="help-box"):
            yield Label(
                "Keys. Enter: change the key, Backspace: back to default, Esc: close"
                "  (saved in keymap.toml)",
                id="help-title",
            )
            yield OptionList(id="help-list")

    def on_mount(self) -> None:
        self._fill()
        self.query_one("#help-list", OptionList).focus()

    def _fill(self, keep: str | None = None) -> None:
        from sqlide.ui.keymap import catalogue, format_keys  # late: keymap imports the screens

        rows = [i for i in catalogue() if i.description]
        width = max(len(i.description) for i in rows)
        listing = self.query_one("#help-list", OptionList)
        listing.clear_options()
        for i in rows:
            mark = "*" if i.overridden else " "
            listing.add_option(
                Option(f"{i.description:<{width}}  {mark}{format_keys(i.keys)}", id=i.id)
            )
        for desc, keys in EXTRA:
            listing.add_option(Option(f"{desc:<{width}}   {keys}", disabled=True))
        if keep:
            listing.highlighted = listing.get_option_index(keep)

    def _current(self) -> tuple[str, str] | None:
        listing = self.query_one("#help-list", OptionList)
        if listing.highlighted is None:
            return None
        option = listing.get_option_at_index(listing.highlighted)
        return (option.id, str(option.prompt)) if option.id else None

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        found = self._current()
        if found is None:
            return
        action_id, text = found

        def done(key: str | None) -> None:
            if key:
                self._rebind(action_id, key)

        title = text.split("  ")[0].strip()
        self.app.push_screen(RebindScreen(title, text.rsplit("  ", 1)[-1].strip()), done)

    def _rebind(self, action_id: str, key: str) -> None:
        from sqlide.ui.keymap import catalogue

        for info in catalogue():
            if info.id != action_id and key in info.keys.split(","):
                self.notify(f"{key} is already used by “{info.description}”", severity="warning")
                return
        save_override(action_id, key)
        self._apply(action_id)

    def action_reset(self) -> None:
        found = self._current()
        if found:
            save_override(found[0], None)
            self._apply(found[0])

    def _apply(self, action_id: str) -> None:
        self.app.set_keymap(load_keymap())  # footer-less: the toolbar listens to the signal
        self._fill(action_id)

    def action_close(self) -> None:
        self.dismiss(None)
