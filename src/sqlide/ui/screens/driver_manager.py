"""Driver manager: see what is installed, download, remove, add custom drivers."""

from __future__ import annotations

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, OptionList, Select
from textual.widgets.option_list import Option

from sqlide.config._toml import ConfigError
from sqlide.drivers.custom import build_custom_driver
from sqlide.drivers.maven import MavenError
from sqlide.drivers.registry import DriverDef
from sqlide.sql.dialects import RULES
from sqlide.ui.screens.dialogs import ConfirmScreen, ProgressScreen
from sqlide.workspace import Workspace


class DriverEditor(ModalScreen[DriverDef | None]):
    """Add a custom driver from jar files or Maven coordinates."""

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog wide"):
            yield Label("Custom driver", classes="title")
            yield Label("Id (e.g. my-db)")
            yield Input(id="id")
            yield Label("Name")
            yield Input(id="name")
            yield Label("Jar files (comma separated)  — or —  Maven group:artifact[:classifier]")
            yield Input(id="source", placeholder="/path/a.jar, /path/b.jar   or   com.foo:bar")
            yield Label("Driver class (empty: detect from jars)")
            yield Input(id="class")
            yield Label("URL template")
            yield Input(id="url", placeholder="jdbc:foo://{host}:{port}/{database}")
            with Horizontal(classes="row"):
                yield Label("Port")
                yield Input("0", type="integer", id="port")
                yield Label("Dialect")
                yield Select(
                    [(d, d) for d in sorted(RULES)],
                    value="generic",
                    allow_blank=False,
                    id="dialect",
                )
            with Horizontal(classes="buttons"):
                yield Button("Add", variant="primary", id="ok")
                yield Button("Cancel", id="cancel")
            yield Label("", id="driver-error", classes="error")

    def on_mount(self) -> None:
        self.query_one("#id", Input).focus()

    def _text(self, widget_id: str) -> str:
        return self.query_one(f"#{widget_id}", Input).value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "ok":
            self.dismiss(None)
            return
        source = self._text("source").strip()
        is_maven = ":" in source and "/" not in source and "\\" not in source
        try:
            driver = build_custom_driver(
                self._text("id"),
                self._text("name"),
                maven=source if is_maven else "",
                jars=[] if is_maven else source.split(","),
                class_name=self._text("class"),
                url_template=self._text("url"),
                default_port=int(self._text("port") or 0),
                dialect=str(self.query_one("#dialect", Select).value),
            )
        except ConfigError as e:
            self.query_one("#driver-error", Label).update(str(e))
            return
        self.dismiss(driver)

    def action_cancel(self) -> None:
        self.dismiss(None)


class DriverManager(ModalScreen[None]):
    BINDINGS = [
        Binding("escape", "close", "Close"),
        Binding("enter,d", "download", "Download"),
        Binding("x", "uninstall", "Remove"),
        Binding("a", "add", "Add custom"),
    ]

    def __init__(self, ws: Workspace) -> None:
        super().__init__()
        self.ws = ws
        self._ids: list[str] = []

    def compose(self) -> ComposeResult:
        with Vertical(id="drivers", classes="dialog wide"):
            yield Label("Drivers", classes="title")
            yield OptionList(id="driver-list")
            yield Label("Enter/d download · x remove · a add custom · Esc close", classes="hint")
            yield Label("", id="driver-message")

    def on_mount(self) -> None:
        self._reload()
        self.query_one("#driver-list", OptionList).focus()

    # --- view ---
    def _state(self, d: DriverDef) -> Text:
        reg = self.ws.registry
        text = Text(f"{d.name}  ")
        if d.jars:
            ok = reg.is_installed(d.id)
            text.append(
                "custom jars" if ok else "custom: jar missing", style="cyan" if ok else "red"
            )
        elif versions := reg.installed_versions(d.id):
            text.append(f"✔ {versions[-1]}", style="green")
        else:
            text.append("not installed", style="yellow")
        return text

    def _reload(self, keep: str | None = None) -> None:
        drivers = self.ws.registry.all()
        self._ids = list(drivers)
        lst = self.query_one("#driver-list", OptionList)
        lst.clear_options()
        lst.add_options([Option(self._state(d)) for d in drivers.values()])
        if self._ids:
            lst.highlighted = self._ids.index(keep) if keep in self._ids else 0

    def _selected(self) -> DriverDef | None:
        i = self.query_one("#driver-list", OptionList).highlighted
        return self.ws.registry.all().get(self._ids[i]) if i is not None else None

    def _say(self, text: str, error: bool = False) -> None:
        self.query_one("#driver-message", Label).update(Text(text, style="red" if error else ""))

    # --- actions ---
    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self.action_download()

    @work(exclusive=True, group="driver")
    async def action_download(self) -> None:
        d = self._selected()
        if d is None:
            return
        if not d.is_maven:
            self._say(f"'{d.name}' uses local jars: nothing to download")
            return
        progress = ProgressScreen(f"Downloading {d.name}…")
        await self.app.push_screen(progress)
        try:
            await self.ws.install_driver(
                d.id, lambda done, total: self.app.call_from_thread(progress.advance, done, total)
            )
        except (MavenError, OSError) as e:
            self._say(str(e), error=True)
        else:
            self._say(f"{d.name} installed")
        finally:
            progress.dismiss()
        self._reload(d.id)

    @work(exclusive=True, group="driver")
    async def action_uninstall(self) -> None:
        d = self._selected()
        if d is None or not d.is_maven or not self.ws.registry.installed_versions(d.id):
            return
        if await self.app.push_screen_wait(ConfirmScreen(f"Remove downloaded jars of {d.name}?")):
            self.ws.registry.uninstall(d.id)
            self._reload(d.id)

    @work(exclusive=True, group="driver")
    async def action_add(self) -> None:
        driver = await self.app.push_screen_wait(DriverEditor())
        if driver is None:
            return
        try:
            self.ws.registry.add_custom(driver)
        except ConfigError as e:
            self._say(str(e), error=True)
            return
        self._reload(driver.id)
        self._say(
            f"Added {driver.name}" + (" (press Enter to download)" if driver.is_maven else "")
        )

    def action_close(self) -> None:
        self.dismiss(None)
