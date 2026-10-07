"""Create/edit a saved connection."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Input, Label, Select, Static, Switch

from sqlide.config._toml import ConfigError
from sqlide.config.connections import Connection
from sqlide.drivers.registry import DriverDef


def url_hint(d: DriverDef) -> str:
    """Starting URL for a driver: its template with sensible defaults."""
    return d.url_template.format(host="localhost", port=d.default_port, database="")


class ConnectionEditor(ModalScreen[Connection | None]):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(
        self,
        drivers: dict[str, DriverDef],
        existing: Connection | None = None,
        taken_names: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._drivers = drivers
        self._existing = existing
        self._taken = taken_names or set()
        self._auto_url = ""  # last URL we generated; replaced only while the user has not edited

    def compose(self) -> ComposeResult:
        c = self._existing
        first = next(iter(self._drivers))
        with Vertical(classes="dialog wide"):
            yield Label("Connection" if c is None else f"Edit {c.name}", classes="title")
            yield Label("Name")
            yield Input(c.name if c else "", id="name")
            yield Label("Driver")
            yield Select(
                [(d.name, d.id) for d in self._drivers.values()],
                value=c.driver if c else first,
                allow_blank=False,
                id="driver",
            )
            yield Label("JDBC URL")
            yield Input(c.url if c else "", id="url")
            yield Label("User (empty = no credentials, no password prompt)")
            yield Input(c.user if c else "", id="user")
            yield Label("Password source: empty = ask on connect, or ${env:VAR}")
            yield Input(c.password_ref if c else "", id="password_ref")
            yield Label("Password command (optional, stdout is the password)")
            yield Input(c.password_cmd if c else "", id="password_cmd")
            with Horizontal(classes="row"):
                yield Label("Autocommit")
                yield Switch(c.autocommit if c else True, id="autocommit")
            yield Static("", id="error", classes="error")
            with Horizontal(classes="buttons"):
                yield Button("Save", variant="primary", id="save")
                yield Button("Cancel", id="cancel")

    def on_mount(self) -> None:
        if self._existing is None:
            self._apply_template(self.query_one("#driver", Select).value)
        self.query_one("#name", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "driver" and event.value in self._drivers:
            self._apply_template(event.value)

    def _apply_template(self, driver_id: object) -> None:
        url = self.query_one("#url", Input)
        if url.value in ("", self._auto_url) and driver_id in self._drivers:
            self._auto_url = url_hint(self._drivers[str(driver_id)])
            url.value = self._auto_url

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss(None)
            return
        self._save()

    def _val(self, id_: str) -> str:
        return self.query_one(f"#{id_}", Input).value.strip()

    def _save(self) -> None:
        name = self._val("name")
        try:
            if name in self._taken:
                raise ConfigError(f"connection '{name}' already exists")
            if not self._val("url"):
                raise ConfigError("JDBC URL is empty")
            conn = Connection(
                name=name,
                driver=str(self.query_one("#driver", Select).value),
                url=self._val("url"),
                user=self._val("user"),
                password_ref=self._val("password_ref"),
                password_cmd=self._val("password_cmd"),
                properties=self._existing.properties if self._existing else {},
                autocommit=self.query_one("#autocommit", Switch).value,
                schemas=None if not self._existing else self._existing.schemas,
                catalogs=None if not self._existing else self._existing.catalogs,
                table_filter=self._existing.table_filter if self._existing else "",
            )
        except ConfigError as e:
            self.query_one("#error", Static).update(str(e))
            return
        self.dismiss(conn)

    def action_cancel(self) -> None:
        self.dismiss(None)
