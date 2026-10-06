"""JSON array and JSON Lines, streamed row by row."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from sqlide.db.result import Column
from sqlide.export.base import Exporter, ExportOptions, Row, register
from sqlide.grid.copyfmt import json_default


def _dump(names: list[str], row: Row) -> str:
    return json.dumps(dict(zip(names, row, strict=True)), default=json_default, ensure_ascii=False)


@register
class JsonExporter(Exporter):
    name, label, extension = "json", "JSON (array)", ".json"

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        names, count = [c.name for c in columns], 0
        with tmp.open("w", encoding="utf-8") as f:
            f.write("[")
            for row in rows:
                f.write(("," if count else "") + "\n  " + _dump(names, row))
                count += 1
            f.write("\n]\n" if count else "]\n")
        return count


@register
class JsonLinesExporter(Exporter):
    name, label, extension = "jsonl", "JSON Lines", ".jsonl"

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        names, count = [c.name for c in columns], 0
        with tmp.open("w", encoding="utf-8") as f:
            for row in rows:
                f.write(_dump(names, row) + "\n")
                count += 1
        return count
