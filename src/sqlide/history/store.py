"""Persistent log of executed statements."""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from sqlide.config import paths

_SCHEMA = """
CREATE TABLE IF NOT EXISTS history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    connection TEXT NOT NULL,
    sql TEXT NOT NULL,
    ok INTEGER NOT NULL,
    elapsed_ms INTEGER NOT NULL,
    error TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS history_ts ON history (ts DESC);
"""


@dataclass(frozen=True, slots=True)
class HistoryEntry:
    id: int
    ts: float
    connection: str
    sql: str
    ok: bool
    elapsed_ms: int
    error: str = ""


def _like(word: str) -> str:
    return "%" + word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


class HistoryStore:
    """Opens its file on first use. Call from one thread (the UI thread)."""

    def __init__(self, path: Path | None = None, limit: int = 5000) -> None:
        self._path = path
        self.limit = limit
        self._db: sqlite3.Connection | None = None

    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            path = self._path or paths.data_dir() / "history.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path)
            self._db.executescript(_SCHEMA)
        return self._db

    def add(
        self,
        connection: str,
        sql: str,
        ok: bool,
        elapsed_ms: int,
        error: str = "",
        ts: float | None = None,
    ) -> None:
        sql = sql.strip()
        if not sql:
            return
        db = self._conn()
        db.execute(
            "INSERT INTO history (ts, connection, sql, ok, elapsed_ms, error) VALUES (?,?,?,?,?,?)",
            (time.time() if ts is None else ts, connection, sql, int(ok), elapsed_ms, error),
        )
        db.execute(
            "DELETE FROM history WHERE id <= (SELECT MAX(id) FROM history) - ?", (self.limit,)
        )
        db.commit()

    def search(
        self,
        text: str = "",
        connection: str | None = None,
        only_ok: bool = False,
        limit: int = 200,
    ) -> list[HistoryEntry]:
        """Newest first. Every word of `text` must occur in the statement (case-insensitive)."""
        where, args = [], []
        for word in text.split():
            where.append("sql LIKE ? ESCAPE '\\'")
            args.append(_like(word))
        if connection is not None:
            where.append("connection = ?")
            args.append(connection)
        if only_ok:
            where.append("ok = 1")
        clause = ("WHERE " + " AND ".join(where)) if where else ""
        rows = self._conn().execute(
            "SELECT id, ts, connection, sql, ok, elapsed_ms, error FROM history "
            f"{clause} ORDER BY id DESC LIMIT ?",
            (*args, limit),
        )
        return [HistoryEntry(r[0], r[1], r[2], r[3], bool(r[4]), r[5], r[6]) for r in rows]

    def delete(self, entry_id: int) -> None:
        db = self._conn()
        db.execute("DELETE FROM history WHERE id = ?", (entry_id,))
        db.commit()

    def clear(self) -> None:
        db = self._conn()
        db.execute("DELETE FROM history")
        db.commit()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
