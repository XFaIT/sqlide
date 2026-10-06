"""CSV and TSV."""

from __future__ import annotations

import csv
from collections.abc import Iterator
from pathlib import Path

from sqlide.db.result import Column
from sqlide.export.base import Exporter, ExportOptions, Row, register
from sqlide.grid.formatting import raw_text


class _Delimited(Exporter):
    forced_delimiter: str | None = None

    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int:
        delimiter = self.forced_delimiter or opts.delimiter or ","
        count = 0
        with tmp.open("w", encoding="utf-8-sig" if opts.bom else "utf-8", newline="") as f:
            w = csv.writer(f, delimiter=delimiter, lineterminator="\n")
            if opts.header:
                w.writerow([c.name for c in columns])
            for row in rows:
                w.writerow([raw_text(v) for v in row])
                count += 1
        return count


@register
class CsvExporter(_Delimited):
    name, label, extension = "csv", "CSV", ".csv"


@register
class TsvExporter(_Delimited):
    name, label, extension = "tsv", "TSV (tab separated)", ".tsv"
    forced_delimiter = "\t"
