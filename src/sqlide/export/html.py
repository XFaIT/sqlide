"""Standalone HTML table."""

from __future__ import annotations

import html
from collections.abc import Iterator
from pathlib import Path

from sqlide.db.result import Column
from sqlide.export.base import Exporter, ExportOptions, Row, register
from sqlide.grid.formatting import raw_text

_HEAD = (
    '<!doctype html>\n<meta charset="utf-8">\n<style>'
    "table{border-collapse:collapse;font:14px sans-serif}"
    "th,td{border:1px solid #ccc;padding:4px 8px;text-align:left}"
    "th{background:#f0f0f0}td.null{background:#fafafa}"
    "</style>\n<table>\n"
)


@register
class HtmlExporter(Exporter):
    name, label, extension = "html", "HTML table", ".html"

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        count = 0
        with tmp.open("w", encoding="utf-8") as f:
            f.write(_HEAD)
            f.write("<thead><tr>" + "".join(f"<th>{html.escape(c.name)}</th>" for c in columns))
            f.write("</tr></thead>\n<tbody>\n")
            for row in rows:
                cells = (
                    '<td class="null"></td>'
                    if v is None
                    else f"<td>{html.escape(raw_text(v))}</td>"
                    for v in row
                )
                f.write("<tr>" + "".join(cells) + "</tr>\n")
                count += 1
            f.write("</tbody>\n</table>\n")
        return count
