"""Markdown table."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlide.db.result import Column
from sqlide.export.base import Exporter, ExportOptions, Row, register
from sqlide.grid.copyfmt import md_cell


@register
class MarkdownExporter(Exporter):
    name, label, extension = "markdown", "Markdown table", ".md"

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        count = 0
        with tmp.open("w", encoding="utf-8") as f:
            f.write("| " + " | ".join(md_cell(c.name) for c in columns) + " |\n")
            f.write("| " + " | ".join("---" for _ in columns) + " |\n")
            for row in rows:
                f.write("| " + " | ".join(md_cell(v) for v in row) + " |\n")
                count += 1
        return count
