"""Main screen: connections sidebar + console."""

from __future__ import annotations

import contextlib

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Footer, Header, ListView

from sqlide.config._toml import ConfigError
from sqlide.config.connections import Connection
from sqlide.db.result import DbError
from sqlide.drivers.loader import DriverError
from sqlide.drivers.maven import MavenError
from sqlide.jvm.locate import JvmNotFound
from sqlide.jvm.runtime import ensure_jvm
from sqlide.ui.screens.connection_editor import ConnectionEditor
from sqlide.ui.screens.dialogs import ConfirmScreen, PasswordPrompt, ProgressScreen
from sqlide.ui.widgets.connections_list import ConnectionItem, ConnectionsList
from sqlide.ui.widgets.console_tab import ConsoleTab
from sqlide.workspace import Workspace

EXPECTED_ERRORS = (ConfigError, MavenError, DriverError, DbError, JvmNotFound)


class MainScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "new_connection", "New connection"),
        Binding("alt+1", "focus_sidebar", "Connections"),
        Binding("alt+2", "focus_editor", "Editor"),
        Binding("alt+3", "focus_results", "Results"),
    ]

    def __init__(self, ws: Workspace) -> None:
        super().__init__()
        self.ws = ws

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            yield ConnectionsList(id="sidebar")
            yield ConsoleTab(self.ws, id="console")
        yield Footer()

    @property
    def sidebar(self) -> ConnectionsList:
        return self.query_one("#sidebar", ConnectionsList)

    @property
    def console(self) -> ConsoleTab:
        return self.query_one("#console", ConsoleTab)

    def on_mount(self) -> None:
        self.app.title = "sqlide"
        self._reload()
        self.sidebar.focus()
        self.run_worker(self._warm_jvm, thread=True, group="jvm")
        if not self.ws.connections():
            self.console.panel.log_line("No connections yet: press Ctrl+N to add one.", "yellow")

    def _warm_jvm(self) -> None:
        # start in the background so the first connect is fast; errors surface on connect
        with contextlib.suppress(JvmNotFound):
            ensure_jvm()

    def _reload(self) -> None:
        self.sidebar.reload(self.ws.connections())

    def _report(self, e: Exception) -> None:
        self.console.panel.log_error(f"✖ {e}")
        self.app.notify(str(e).splitlines()[0], title="Error", severity="error", timeout=10)

    # --- focus ---
    def action_focus_sidebar(self) -> None:
        self.sidebar.focus()

    def action_focus_editor(self) -> None:
        self.console.editor.focus()

    def action_focus_results(self) -> None:
        self.console.panel.tabs.focus()

    # --- connection CRUD ---
    @work(exclusive=True, group="dialog")
    async def action_new_connection(self) -> None:
        await self._edit(None)

    @work(exclusive=True, group="dialog")
    async def on_connections_list_edit_requested(self, msg: ConnectionsList.EditRequested) -> None:
        await self._edit(msg.conn)

    async def _edit(self, existing: Connection | None) -> None:
        taken = {c.name for c in self.ws.connections()} - ({existing.name} if existing else set())
        conn = await self.app.push_screen_wait(
            ConnectionEditor(self.ws.registry.all(), existing, taken)
        )
        if conn is not None:
            self.ws.save_connection(conn, replaces=existing.name if existing else None)
            self._reload()

    @work(exclusive=True, group="dialog")
    async def on_connections_list_delete_requested(
        self, msg: ConnectionsList.DeleteRequested
    ) -> None:
        if await self.app.push_screen_wait(ConfirmScreen(f"Delete connection '{msg.conn.name}'?")):
            self.ws.delete_connection(msg.conn.name)
            self._reload()

    # --- connecting ---
    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if isinstance(event.item, ConnectionItem):
            self._connect(event.item.conn)

    @work(exclusive=True, group="connect")
    async def _connect(self, conn: Connection) -> None:
        console = self.console
        try:
            if not self.ws.driver_ready(conn) and not await self._offer_driver(conn):
                return
            password = await self.ws.lookup_password(conn)
            if password is None and self.ws.needs_password_prompt(conn):
                password = await self.app.push_screen_wait(
                    PasswordPrompt(f"Password for {conn.user}@{conn.name}")
                )
                if password is None:
                    return
                self.ws.resolver.store(conn.name, password)
            console.status.update_state(message=f"connecting to {conn.name}…")
            session = await self.ws.connect(conn, password)
        except EXPECTED_ERRORS as e:
            console.status.update_state(message="")
            self.ws.resolver.forget(conn.name)  # a wrong password must not be cached
            self._report(e)
            return
        await console.attach(conn, session)
        self.app.sub_title = conn.name
        console.editor.focus()

    async def _offer_driver(self, conn: Connection) -> bool:
        defn = self.ws.driver(conn.driver)
        if not defn.is_maven:
            raise DriverError(f"driver '{defn.id}' has no jar files on disk: {defn.jars}")
        ok = await self.app.push_screen_wait(
            ConfirmScreen(
                f"Driver '{defn.name}' is not installed.\n"
                f"Download {defn.group}:{defn.artifact} from Maven Central?",
                yes="Download",
                no="Cancel",
            )
        )
        if not ok:
            return False
        progress = ProgressScreen(f"Downloading {defn.name}…")
        await self.app.push_screen(progress)
        try:
            await self.ws.install_driver(
                defn.id, lambda d, t: self.app.call_from_thread(progress.advance, d, t)
            )
        finally:
            progress.dismiss()
        self.console.panel.log_line(f"Driver installed: {defn.name}", "green")
        return True
