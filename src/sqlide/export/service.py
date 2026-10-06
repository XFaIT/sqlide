"""Run an export for each data scope. Blocking work happens off the UI thread."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

from sqlide.db.result import Column
from sqlide.db.session import DbSession
from sqlide.export.base import Exporter, ExportOptions, Row


async def export_rows(
    exporter: Exporter,
    columns: Sequence[Column],
    rows: Sequence[Row],
    path: Path,
    opts: ExportOptions,
) -> int:
    """Rows already in memory (grid view or selection)."""
    return await asyncio.to_thread(exporter.write, columns, rows, path, opts)


async def export_query(
    exporter: Exporter, session: DbSession, sql: str, path: Path, opts: ExportOptions
) -> int:
    """Re-run `sql` on `session` and stream the whole first result set into the file.

    Use a dedicated session: running a statement closes the session's open cursors.
    """
    return await session.stream(
        sql, lambda columns, rows: exporter.write(columns, rows, path, opts)
    )
