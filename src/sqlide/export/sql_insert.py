"""SQL INSERT statements."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlide.db.result import Column
from sqlide.export.base import Exporter, ExportOptions, Row, register
from sqlide.grid.copyfmt import sql_ident, sql_literal


@register
class SqlInsertExporter(Exporter):
    name, label, extension = "sql", "SQL INSERT statements", ".sql"

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        cols = ", ".join(sql_ident(c.name) for c in columns)
        head = f"INSERT INTO {opts.table_name} ({cols}) VALUES"
        batch = max(1, opts.batch_size)
        count, pending = 0, []
        with tmp.open("w", encoding="utf-8") as f:

            def flush() -> None:
                if pending:
                    f.write(head + "\n  " + ",\n  ".join(pending) + ";\n")
                    pending.clear()

            for row in rows:
                pending.append("(" + ", ".join(sql_literal(v) for v in row) + ")")
                count += 1
                if len(pending) >= batch:
                    flush()
            flush()
        return count
