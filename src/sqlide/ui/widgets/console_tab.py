"""One console: editor + results + status, bound to one DB session."""

from __future__ import annotations

import asyncio
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical

from sqlide import export
from sqlide.config.connections import Connection
from sqlide.db.result import DbError
from sqlide.db.session import DbSession
from sqlide.export import ExportCancelled, ExportOptions
from sqlide.export.service import export_query, export_rows
from sqlide.ui.screens.export_dialog import ExportContext, ExportRequest, ExportScreen
from sqlide.ui.widgets.result_grid import ResultGrid
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
        self._exporting = False
        self._export_cancel = False
        self._export_session: DbSession | None = None

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

    def on_result_grid_summary(self, message: ResultGrid.Summary) -> None:
        message.stop()
        self.status.update_state(message=message.text)

    def action_cancel(self) -> None:
        if self._exporting:
            self._export_cancel = True
            if self._export_session is not None:
                self._export_session.cancel()
            self.status.update_state(message="cancelling export…")
        elif self.session is not None and self._executing:
            self.session.cancel()
            self.status.update_state(message="cancelling…")

    # --- export ---
    def on_result_grid_export_requested(self, message: ResultGrid.ExportRequested) -> None:
        message.stop()
        grid = message.grid
        if self._exporting:
            self.app.notify("An export is already running", severity="warning")
            return
        r0, c0, r1, c1 = grid.selection_rect()
        ctx = ExportContext(
            n_view=len(grid.model),
            selection=((r1 - r0 + 1, c1 - c0 + 1) if (r1 > r0 or c1 > c0) else None),
            can_requery=bool(grid.sql and self.conn is not None),
            more_rows=grid.source is not None,
        )
        self.app.push_screen(
            ExportScreen(ctx), lambda req: self._start_export(grid, req) if req else None
        )

    def _start_export(self, grid: ResultGrid, req: ExportRequest) -> None:
        self.run_worker(self._do_export(grid, req), group="export", exit_on_error=False)

    async def _do_export(self, grid: ResultGrid, req: ExportRequest) -> None:
        exporter = export.get(req.format)
        self._exporting, self._export_cancel = True, False

        def progress(n: int) -> None:  # called from a worker thread
            self.app.call_from_thread(self.status.update_state, message=f"exporting… {n:,} rows")

        opts = ExportOptions(
            header=req.header,
            delimiter=req.delimiter,
            bom=req.bom,
            table_name=req.table_name,
            progress=progress,
            should_cancel=lambda: self._export_cancel,
        )
        self.status.update_state(message="exporting…")
        try:
            if req.scope == "all":
                count = await self._export_all(exporter, grid, req.path, opts)
            elif req.scope == "selection":
                columns, rows = grid.selection_data()
                count = await export_rows(exporter, columns, rows, req.path, opts)
            else:
                rows = grid.model.rows(0, len(grid.model) - 1)
                count = await export_rows(exporter, grid.model.columns, rows, req.path, opts)
        except ExportCancelled:
            self.app.notify("Export cancelled", severity="warning")
            self.status.update_state(message="export cancelled")
        except Exception as e:  # file system, driver, or DB errors: show, never crash the UI
            self.panel.log_error(f"✖ Export failed: {e}")
            self.app.notify(str(e), title="Export failed", severity="error")
            self.status.update_state(message="export failed")
        else:
            size = req.path.stat().st_size
            msg = f"Exported {count:,} rows to {req.path} ({size / 1024:.1f} KB)"
            self.panel.log_line(msg, "green")
            self.app.notify(msg)
            self.status.update_state(message=f"exported {count:,} rows")
        finally:
            self._exporting = False

    async def _export_all(
        self, exporter: export.Exporter, grid: ResultGrid, path: Path, opts: ExportOptions
    ) -> int:
        """Re-run the statement on a private connection and stream it into the file."""
        assert self.conn is not None
        password = await self.ws.lookup_password(self.conn)
        session = await self.ws.connect(self.conn, password)
        self._export_session = session
        try:
            return await export_query(exporter, session, grid.sql, path, opts)
        except DbError:
            if self._export_cancel:
                raise ExportCancelled from None
            raise
        finally:
            self._export_session = None
            await asyncio.shield(session.close())

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
                        grid = await self.panel.add_result(
                            f"Result {n_results}",
                            item.columns,
                            item.rows,
                            item.cursor,
                            self.ws.settings.fetch_size,
                            sql,
                        )
                        last = grid.summary_text
                    else:
                        last = f"{item.update_count} rows affected"
                        self.panel.log_line(f"  {last}")
                self.panel.log_line(f"✔ {ex.elapsed_s * 1000:.0f} ms", "green")
                last = f"{last} in {ex.elapsed_s * 1000:.0f} ms"
        finally:
            self._executing = False
            self.status.update_state(message=last)
            self.panel.show_first_result()
