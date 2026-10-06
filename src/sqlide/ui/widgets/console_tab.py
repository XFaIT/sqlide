"""One console: editor + results + status, bound to one DB session."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical

from sqlide.config.connections import Connection
from sqlide.db.result import DbError
from sqlide.db.session import DbSession
from sqlide.ui.widgets.result_panel import ResultPanel
from sqlide.ui.widgets.sql_editor import SqlEditor
from sqlide.ui.widgets.status_bar import StatusBar
from sqlide.workspace import Workspace


def one_line(sql: str, limit: int = 100) -> str:
    text = " ".join(sql.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


class ConsoleTab(Vertical):
    BINDINGS = [Binding("ctrl+f2", "cancel", "Cancel query")]

    def __init__(self, ws: Workspace, **kw) -> None:
        super().__init__(**kw)
        self.ws = ws
        self.conn: Connection | None = None
        self.session: DbSession | None = None
        self._executing = False

    def compose(self) -> ComposeResult:
        yield SqlEditor(blank_line=self.ws.settings.split_on_blank_line, id="editor")
        yield ResultPanel(id="results")
        yield StatusBar(id="status")

    @property
    def editor(self) -> SqlEditor:
        return self.query_one("#editor", SqlEditor)

    @property
    def panel(self) -> ResultPanel:
        return self.query_one("#results", ResultPanel)

    @property
    def status(self) -> StatusBar:
        return self.query_one("#status", StatusBar)

    @property
    def running(self) -> bool:
        return self._executing

    # --- connection ---
    async def attach(self, conn: Connection, session: DbSession) -> None:
        await self.detach()
        self.conn, self.session = conn, session
        self.editor.dialect = self.ws.driver(conn.driver).dialect
        self.status.update_state(
            connection=f"{conn.name} ({session.product})",
            tx="Auto" if session.autocommit else "Manual",
            message="",
        )
        self.panel.log_line(f"Connected: {conn.name}: {session.product}", "green")

    async def detach(self) -> None:
        if self.session is not None:
            await self.session.close()
        self.conn = self.session = None
        self.status.update_state(connection="not connected", tx="", message="")

    # --- execution ---
    def on_sql_editor_run_requested(self, message: SqlEditor.RunRequested) -> None:
        message.stop()
        if self.session is None:
            self.app.notify("Not connected: pick a connection in the sidebar", severity="warning")
        elif self._executing:
            self.app.notify("A query is running (Ctrl+F2 cancels it)", severity="warning")
        else:
            self.run_worker(self._run(message.statements), group="run")

    def action_cancel(self) -> None:
        if self.session is not None and self._executing:
            self.session.cancel()
            self.status.update_state(message="cancelling…")

    async def _run(self, statements: list[str]) -> None:
        session = self.session
        assert session is not None
        self._executing = True
        self.status.update_state(message="running…")
        await self.panel.reset_results()
        n_results = 0
        last = ""
        try:
            for sql in statements:
                self.panel.log_line(f"▶ {one_line(sql)}", "bold")
                try:
                    ex = await session.execute(sql, self.ws.settings.fetch_size)
                except DbError as e:
                    self.panel.log_error(f"✖ {e}" + (f"  [{e.sql_state}]" if e.sql_state else ""))
                    self.app.notify(str(e), title="Query failed", severity="error")
                    last = "failed"
                    break
                for w in ex.warnings:
                    self.panel.log_line(f"  {w}", "yellow")
                for item in ex.items:
                    if item.has_rows:
                        n_results += 1
                        await self.panel.add_result(f"Result {n_results}", item.columns, item.rows)
                        more = "+ (more rows not loaded)" if item.cursor else ""
                        last = f"{len(item.rows)}{more} rows"
                    else:
                        last = f"{item.update_count} rows affected"
                        self.panel.log_line(f"  {last}")
                self.panel.log_line(f"✔ {ex.elapsed_s * 1000:.0f} ms", "green")
                last = f"{last} in {ex.elapsed_s * 1000:.0f} ms"
        finally:
            self._executing = False
            self.status.update_state(message=last)
            self.panel.show_first_result()
