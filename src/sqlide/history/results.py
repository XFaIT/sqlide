"""Result tabs saved between runs: pinned ones and the last results of each console.

sqlite, one row per tab. Rows are JSON with tagged values so dates, decimals and bytes come
back as the same Python types. Every call opens its own connection, so it is safe to call
from a worker thread.
"""

from __future__ import annotations

import base64
import contextlib
import datetime as dt
import json
import sqlite3
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlide.config import paths
from sqlide.db.result import Column

MAX_ROWS = 5000  # per saved tab; the rest is dropped (the tab says so)
_SCHEMA = """
CREATE TABLE IF NOT EXISTS result (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    console TEXT NOT NULL,
    pos INTEGER NOT NULL,
    title TEXT NOT NULL,
    sql TEXT NOT NULL,
    ts REAL NOT NULL,
    pinned INTEGER NOT NULL,
    truncated INTEGER NOT NULL,
    columns TEXT NOT NULL,
    rows TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS result_console ON result (console, pos);
"""


@dataclass(slots=True)
class SavedResult:
    title: str
    sql: str
    ts: float
    pinned: bool
    columns: list[Column]
    rows: list[tuple[Any, ...]]
    truncated: bool = False


def encode_value(v: Any) -> Any:
    if v is None or isinstance(v, bool | int | str):
        return v
    if isinstance(v, float):
        return v if v == v and abs(v) != float("inf") else {"$": "float", "v": repr(v)}
    if isinstance(v, Decimal):
        return {"$": "dec", "v": str(v)}
    if isinstance(v, dt.datetime):
        return {"$": "dt", "v": v.isoformat()}
    if isinstance(v, dt.date):
        return {"$": "date", "v": v.isoformat()}
    if isinstance(v, dt.time):
        return {"$": "time", "v": v.isoformat()}
    if isinstance(v, bytes | bytearray):
        return {"$": "b64", "v": base64.b64encode(bytes(v)).decode("ascii")}
    return str(v)  # arrays, structs, anything else: what the grid would show


def decode_value(v: Any) -> Any:
    if not isinstance(v, dict):
        return v
    tag = v.get("$")
    raw: Any = v.get("v")
    try:
        match tag:
            case "dec":
                return Decimal(raw)
            case "dt":
                return dt.datetime.fromisoformat(raw)
            case "date":
                return dt.date.fromisoformat(raw)
            case "time":
                return dt.time.fromisoformat(raw)
            case "b64":
                return base64.b64decode(raw)
            case "float":
                return float(raw)
    except (TypeError, ValueError):
        pass
    return raw


class ResultStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        path = self._path or paths.data_dir() / "results.sqlite"
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=10)
        try:
            db.executescript(_SCHEMA)
            yield db
            db.commit()
        finally:
            db.close()

    def replace(self, console: str, results: Sequence[SavedResult]) -> None:
        """Make `results` the saved tabs of `console` (in tab order)."""
        with self._db() as db:
            db.execute("DELETE FROM result WHERE console = ?", (console,))
            for pos, r in enumerate(results):
                rows = r.rows[:MAX_ROWS]
                db.execute(
                    "INSERT INTO result (console, pos, title, sql, ts, pinned, truncated,"
                    " columns, rows) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        console,
                        pos,
                        r.title,
                        r.sql,
                        r.ts,
                        int(r.pinned),
                        int(r.truncated or len(r.rows) > MAX_ROWS),
                        json.dumps([[c.name, c.type_name, c.jdbc_type] for c in r.columns]),
                        json.dumps([[encode_value(v) for v in row] for row in rows]),
                    ),
                )

    def load(self, console: str) -> list[SavedResult]:
        with self._db() as db:
            found = db.execute(
                "SELECT title, sql, ts, pinned, truncated, columns, rows FROM result "
                "WHERE console = ? ORDER BY pos",
                (console,),
            ).fetchall()
        out = []
        for title, sql, ts, pinned, truncated, columns, rows in found:
            try:
                cols = [Column(n, t, int(j)) for n, t, j in json.loads(columns)]
                data = [tuple(decode_value(v) for v in row) for row in json.loads(rows)]
            except (ValueError, TypeError):
                continue  # a damaged row is skipped, not fatal
            out.append(SavedResult(title, sql, ts, bool(pinned), cols, data, bool(truncated)))
        return out

    def forget(self, console: str) -> None:
        with self._db() as db:
            db.execute("DELETE FROM result WHERE console = ?", (console,))
