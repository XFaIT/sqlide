"""Main screen: connections sidebar + tabs of consoles."""

from __future__ import annotations

import contextlib
from pathlib import Path

from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Footer, Header, ListView, TabbedContent, TabPane

from sqlide.config._toml import ConfigError
from sqlide.config.connections import Connection
from sqlide.config.settings import save_settings
from sqlide.consoles import FILE
from sqlide.db.result import DbError
from sqlide.drivers.loader import DriverError
from sqlide.drivers.maven import MavenError
from sqlide.jvm.locate import JvmNotFound
from sqlide.jvm.runtime import ensure_jvm
from sqlide.sql.snippets import qualified_name, select_all
from sqlide.ui.screens.connection_editor import ConnectionEditor
from sqlide.ui.screens.dialogs import ConfirmScreen, PasswordPrompt, PathPrompt, ProgressScreen
from sqlide.ui.screens.driver_manager import DriverManager
from sqlide.ui.screens.history import HistoryScreen
from sqlide.ui.screens.settings import SettingsScreen
from sqlide.ui.widgets.connections_list import ConnectionItem, ConnectionsList
from sqlide.ui.widgets.console_tab import ConsoleTab
from sqlide.ui.widgets.console_tabs import ConsoleTabs
from sqlide.ui.widgets.schema_tree import SchemaTree
from sqlide.workspace import Workspace

EXPECTED_ERRORS = (ConfigError, MavenError, DriverError, DbError, JvmNotFound)


class MainScreen(Screen):
    BINDINGS = [
        Binding("ctrl+n", "new_connection", "New connection", id="main.new_connection"),
        Binding("ctrl+t", "new_console", "New console", id="main.new_console"),
        Binding("ctrl+f4,alt+w", "close_console", "Close tab", id="main.close_console"),
        Binding("ctrl+alt+e,alt+e", "history", "History", id="main.history"),
        Binding("ctrl+o", "open_file", "Open file", id="main.open_file"),
        Binding("ctrl+s", "save_file", "Save", id="main.save_file"),
        Binding("alt+right", "tab(1)", "Next tab", show=False, id="main.next_tab"),
        Binding("alt+left", "tab(-1)", "Previous tab", show=False, id="main.prev_tab"),
        Binding("alt+1", "focus_sidebar", "Connections", show=False, id="main.focus_sidebar"),
        Binding("alt+4", "focus_schema", "Schema", show=False, id="main.focus_schema"),
        Binding("alt+2", "focus_editor", "Editor", show=False, id="main.focus_editor"),
        Binding("alt+3", "focus_results", "Results", show=False, id="main.focus_results"),
    ]

    def __init__(self, ws: Workspace, files: list[Path] | None = None) -> None:
        super().__init__()
        self.ws = ws
        self._files = files or []

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="side"):
                yield ConnectionsList(id="sidebar")
                yield SchemaTree(id="schema")
            yield ConsoleTabs.build(self.ws, self.ws.consoles.load_state(), self._files, id="tabs")
        yield Footer()

    # --- parts ---
    @property
    def sidebar(self) -> ConnectionsList:
        return self.query_one("#sidebar", ConnectionsList)

    @property
    def schema(self) -> SchemaTree:
        return self.query_one("#schema", SchemaTree)

    @property
    def tabs(self) -> ConsoleTabs:
        return self.query_one("#tabs", ConsoleTabs)

    @property
    def console(self) -> ConsoleTab:
        console = self.tabs.active_console
        assert console is not None, "there is always at least one console"
        return console

    def on_mount(self) -> None:
        self.app.title = "sqlide"
        self._reload()
        self.sidebar.focus()
        self._sync_subtitle()
        self.run_worker(self._warm_jvm, thread=True, group="jvm")
        if not self.ws.connections():
            self.console.panel.log_line("No connections yet: press Ctrl+N to add one.", "yellow")

    def _warm_jvm(self) -> None:
        # start in the background so the first connect is fast; errors surface on connect
        with contextlib.suppress(JvmNotFound):
            ensure_jvm()

    def _reload(self) -> None:
        self.sidebar.reload(self.ws.connections())

    def _sync_subtitle(self) -> None:
        console = self.tabs.active_console
        self.app.sub_title = console.conn_name if console else ""
        if console is not None:
            self.schema.show(console.meta, console.conn_name)

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        if event.tabbed_content is self.tabs:  # not the result tabs inside a console
            self._sync_subtitle()

    def _report(self, e: Exception, console: ConsoleTab | None = None) -> None:
        (console or self.console).panel.log_error(f"✖ {e}")
        self.app.notify(str(e).splitlines()[0], title="Error", severity="error", timeout=10)

    # --- focus ---
    def action_focus_sidebar(self) -> None:
        self.sidebar.focus()

    def action_focus_schema(self) -> None:
        self.schema.focus()

    def on_schema_tree_table_chosen(self, msg: SchemaTree.TableChosen) -> None:
        msg.stop()
        console = self.console
        dialect = console.editor.dialect
        name = qualified_name([msg.table.namespace, msg.table.name], dialect)
        editor = console.editor
        if msg.action == "insert":
            editor.insert(name)
            editor.focus()
            return
        sql = select_all(name, dialect)
        editor.move_cursor(editor.document.end)
        editor.insert(("\n\n" if editor.text.strip() else "") + sql + ";")
        editor.focus()
        console.run_statements([sql])

    def action_focus_editor(self) -> None:
        self.console.editor.focus()

    def action_focus_results(self) -> None:
        self.console.panel.tabs.focus()

    # --- tabs and files ---
    def action_tab(self, step: int) -> None:
        ids = [p.id for p in self.tabs.query(TabPane) if p.id and p.id.startswith("c")]
        ids = [i for i in ids if self.tabs.get_pane(i).query(ConsoleTab)]
        if len(ids) > 1 and self.tabs.active in ids:
            self.tabs.active = ids[(ids.index(self.tabs.active) + step) % len(ids)]

    @work(group="tabs")
    async def action_new_console(self) -> None:
        current = self.tabs.active_console
        await self.tabs.add_console(conn_name=current.conn_name if current else "")
        self.console.editor.focus()

    @work(group="tabs")
    async def action_close_console(self) -> None:
        console = self.tabs.active_console
        if console is None:
            return
        if console.dirty and not await self.app.push_screen_wait(
            ConfirmScreen(f"Discard unsaved changes in {console.path.name}?", yes="Discard")
        ):
            return
        await self.tabs.close_console(console)
        self._sync_subtitle()

    @work(exclusive=True, group="dialog")
    async def action_open_file(self) -> None:
        raw = await self.app.push_screen_wait(
            PathPrompt("Open SQL file", default=f"{Path.cwd()}/", ok="Open")
        )
        if raw is None:
            return
        path = Path(raw).expanduser()
        if not path.is_file():
            self.app.notify(f"No such file: {path}", severity="error")
            return
        await self.open_path(path)

    async def open_path(self, path: Path) -> None:
        existing = self.tabs.find_file(path)
        if existing is not None and existing.parent is not None:
            pane = existing.parent
            if isinstance(pane, TabPane) and pane.id:
                self.tabs.active = pane.id
            return
        current = self.tabs.active_console
        await self.tabs.add_console(
            kind=FILE, path=path, conn_name=current.conn_name if current else ""
        )
        self.console.editor.focus()

    @work(exclusive=True, group="dialog")
    async def action_save_file(self) -> None:
        console = self.console
        try:
            if console.kind == FILE:
                console.save()
            else:
                raw = await self.app.push_screen_wait(
                    PathPrompt("Save console as", default=f"{Path.cwd()}/query.sql", ok="Save")
                )
                if raw is None:
                    return
                console.save(Path(raw).expanduser())
        except OSError as e:
            self.app.notify(str(e), title="Cannot save", severity="error")
            return
        self.app.notify(f"Saved {console.path}")

    # --- settings and drivers ---
    @work(exclusive=True, group="dialog")
    async def action_settings(self) -> None:
        new = await self.app.push_screen_wait(
            SettingsScreen(self.ws.settings, sorted(self.app.available_themes))
        )
        if new is None:
            return
        self.ws.settings = new
        self.ws.history.limit = new.history_limit
        for console in self.tabs.consoles():
            console.editor.blank_line = new.split_on_blank_line
        self.app.theme = new.theme  # also persisted by the theme watcher
        save_settings(new)

    @work(exclusive=True, group="dialog")
    async def action_drivers(self) -> None:
        await self.app.push_screen_wait(DriverManager(self.ws))

    # --- history ---
    @work(exclusive=True, group="dialog")
    async def action_history(self) -> None:
        console = self.console
        choice = await self.app.push_screen_wait(HistoryScreen(self.ws.history, console.conn_name))
        if choice is None:
            return
        editor = console.editor
        editor.move_cursor(editor.document.end)
        editor.insert(("\n\n" if editor.text.strip() else "") + choice.sql + ";")
        editor.focus()
        if choice.run:
            console.run_statements([choice.sql])

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
            self._connect(event.item.conn, self.console, None)

    def on_console_tab_connect_requested(self, msg: ConsoleTab.ConnectRequested) -> None:
        msg.stop()
        conn = next((c for c in self.ws.connections() if c.name == msg.conn_name), None)
        if conn is not None:
            self._connect(conn, msg.console, msg.then_run)

    @work(exclusive=True, group="connect")
    async def _connect(
        self, conn: Connection, console: ConsoleTab, then_run: list[str] | None
    ) -> None:
        try:
            if not self.ws.driver_ready(conn) and not await self._offer_driver(conn, console):
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
            self._report(e, console)
            return
        await console.attach(conn, session)
        self._sync_subtitle()
        console.editor.focus()
        if then_run:
            console.run_statements(then_run)

    async def _offer_driver(self, conn: Connection, console: ConsoleTab) -> bool:
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
        console.panel.log_line(f"Driver installed: {defn.name}", "green")
        return True
