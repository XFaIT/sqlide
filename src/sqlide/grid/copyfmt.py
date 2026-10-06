"""Text renderings of a block of cells, for the clipboard. Pure functions."""

from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

from sqlide.grid.formatting import raw_text

Row = tuple[Any, ...]

_PLAIN_IDENT = re.compile(r"^[a-z_][a-z0-9_]*$")


def _tsv_cell(v: Any) -> str:
    s = raw_text(v)
    if any(ch in s for ch in '\t\n\r"'):
        return '"' + s.replace('"', '""') + '"'  # Excel/Sheets convention
    return s


def to_tsv(rows: Sequence[Row], header: Sequence[str] | None = None) -> str:
    lines = []
    if header is not None:
        lines.append("\t".join(_tsv_cell(h) for h in header))
    lines += ["\t".join(_tsv_cell(v) for v in row) for row in rows]
    return "\n".join(lines)


def to_csv(rows: Sequence[Row], header: Sequence[str] | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    if header is not None:
        w.writerow(header)
    for row in rows:
        w.writerow([raw_text(v) for v in row])
    return buf.getvalue().rstrip("\n")


def md_cell(v: Any) -> str:
    return raw_text(v).replace("|", "\\|").replace("\r\n", "<br>").replace("\n", "<br>")


def to_markdown(rows: Sequence[Row], header: Sequence[str]) -> str:
    lines = ["| " + " | ".join(md_cell(h) for h in header) + " |"]
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    lines += ["| " + " | ".join(md_cell(v) for v in row) + " |" for row in rows]
    return "\n".join(lines)


def json_default(v: Any) -> Any:
    if isinstance(v, Decimal):
        return int(v) if v == v.to_integral_value() else float(v)
    if isinstance(v, dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, dt.date | dt.time):
        return v.isoformat()
    if isinstance(v, bytes):
        return "0x" + v.hex()
    return str(v)


def to_json(rows: Sequence[Row], header: Sequence[str]) -> str:
    objs = [dict(zip(header, row, strict=True)) for row in rows]
    return json.dumps(objs, default=json_default, ensure_ascii=False, indent=2)


def sql_literal(v: Any) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, int | Decimal):
        return raw_text(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, bytes):
        return f"X'{v.hex()}'"
    return "'" + raw_text(v).replace("'", "''") + "'"


def sql_ident(name: str) -> str:
    return name if _PLAIN_IDENT.match(name) else '"' + name.replace('"', '""') + '"'


def to_insert_sql(rows: Sequence[Row], header: Sequence[str], table: str = "table_name") -> str:
    cols = ", ".join(sql_ident(h) for h in header)
    return "\n".join(
        f"INSERT INTO {table} ({cols}) VALUES ({', '.join(sql_literal(v) for v in row)});"
        for row in rows
    )
