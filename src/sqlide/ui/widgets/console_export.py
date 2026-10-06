"""Export wiring for a console: dialog -> exporter -> status.

Mixed into ConsoleTab. Delete this file (and the base class) to drop export from the UI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING

from sqlide import export
from sqlide.db.result import DbError
from sqlide.db.session import DbSession
from sqlide.export import ExportCancelled, ExportOptions
from sqlide.export.service import export_query, export_rows
from sqlide.ui.screens.export_dialog import ExportContext, ExportRequest, ExportScreen
from sqlide.ui.widgets.result_grid import ResultGrid

if TYPE_CHECKING:
    from sqlide.ui.widgets.console_tab import ConsoleTab


class ExportActions:
    """Expects the host to be a ConsoleTab (ws, conn, status, panel, app, run_worker)."""

    _exporting = False
    _export_cancel = False
    _export_session: DbSession | None = None

    def cancel_export(self) -> bool:
        """Request cancellation of a running export. False if none is running."""
        if not self._exporting:
            return False
        self._export_cancel = True
        if self._export_session is not None:
            self._export_session.cancel()
        self._host.status.update_state(message="cancelling export…")
        return True

    @property
    def _host(self) -> ConsoleTab:
        return self  # type: ignore[return-value]

    def on_result_grid_export_requested(self, message: ResultGrid.ExportRequested) -> None:
        message.stop()
        host, grid = self._host, message.grid
        if self._exporting:
            host.app.notify("An export is already running", severity="warning")
            return
        r0, c0, r1, c1 = grid.selection_rect()
        ctx = ExportContext(
            n_view=len(grid.model),
            selection=((r1 - r0 + 1, c1 - c0 + 1) if (r1 > r0 or c1 > c0) else None),
            can_requery=bool(grid.sql and host.conn is not None),
            more_rows=grid.source is not None,
        )
        host.app.push_screen(
            ExportScreen(ctx), lambda req: self._start_export(grid, req) if req else None
        )

    def _start_export(self, grid: ResultGrid, req: ExportRequest) -> None:
        self._host.run_worker(self._do_export(grid, req), group="export", exit_on_error=False)

    async def _do_export(self, grid: ResultGrid, req: ExportRequest) -> None:
        host = self._host
        exporter = export.get(req.format)
        self._exporting, self._export_cancel = True, False

        def progress(n: int) -> None:  # called from a worker thread
            host.app.call_from_thread(host.status.update_state, message=f"exporting… {n:,} rows")

        opts = ExportOptions(
            header=req.header,
            delimiter=req.delimiter,
            bom=req.bom,
            table_name=req.table_name,
            progress=progress,
            should_cancel=lambda: self._export_cancel,
        )
        host.status.update_state(message="exporting…")
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
            host.app.notify("Export cancelled", severity="warning")
            host.status.update_state(message="export cancelled")
        except Exception as e:  # file system, driver, or DB errors: show, never crash the UI
            host.panel.log_error(f"✖ Export failed: {e}")
            host.app.notify(str(e), title="Export failed", severity="error")
            host.status.update_state(message="export failed")
        else:
            size = req.path.stat().st_size
            msg = f"Exported {count:,} rows to {req.path} ({size / 1024:.1f} KB)"
            host.panel.log_line(msg, "green")
            host.app.notify(msg)
            host.status.update_state(message=f"exported {count:,} rows")
        finally:
            self._exporting = False

    async def _export_all(
        self, exporter: export.Exporter, grid: ResultGrid, path: Path, opts: ExportOptions
    ) -> int:
        """Re-run the statement on a private connection and stream it into the file."""
        host = self._host
        assert host.conn is not None
        password = await host.ws.lookup_password(host.conn)
        session = await host.ws.connect(host.conn, password)
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
