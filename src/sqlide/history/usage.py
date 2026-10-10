"""How often each table/column was used per connection (sqlite). Drives autocomplete ranking
and the "Recent" node of the schema tree. Call from one thread (the UI thread)."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterable
from pathlib import Path

from sqlide.config import paths
from sqlide.sql.usage import Use

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    connection TEXT NOT NULL,
    key TEXT NOT NULL,
    kind TEXT NOT NULL,
    parts TEXT NOT NULL,
    count INTEGER NOT NULL,
    last_ts REAL NOT NULL,
    PRIMARY KEY (connection, key)
);
CREATE TABLE IF NOT EXISTS backfilled (connection TEXT PRIMARY KEY);
"""
HALF_LIFE_S = 30 * 86400.0  # a use a month ago counts half


def _score(count: int, last_ts: float, now: float) -> float:
    return count * 0.5 ** (max(0.0, now - last_ts) / HALF_LIFE_S)


class UsageStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = path
        self._db: sqlite3.Connection | None = None

    def _conn(self) -> sqlite3.Connection:
        if self._db is None:
            path = self._path or paths.data_dir() / "usage.sqlite"
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path)
            self._db.executescript(_SCHEMA)
        return self._db

    def record(self, connection: str, uses: Iterable[Use], ts: float | None = None) -> None:
        now = time.time() if ts is None else ts
        db = self._conn()
        for u in uses:
            db.execute(
                "INSERT INTO usage (connection, key, kind, parts, count, last_ts) "
                "VALUES (?,?,?,?,1,?) ON CONFLICT(connection, key) DO UPDATE SET "
                "count = count + 1, last_ts = MAX(last_ts, excluded.last_ts), "
                "parts = excluded.parts",
                (connection, u.key, u.kind, json.dumps(u.parts), now),
            )
        db.commit()

    def scores(self, connection: str, now: float | None = None) -> dict[str, float]:
        """`kind:schema.table[.column]` (lowercase) -> decayed use count."""
        now = time.time() if now is None else now
        rows = self._conn().execute(
            "SELECT key, count, last_ts FROM usage WHERE connection = ?", (connection,)
        )
        return {k: _score(c, ts, now) for k, c, ts in rows}

    def top_tables(
        self, connection: str, limit: int = 15, now: float | None = None
    ) -> list[tuple[str, ...]]:
        now = time.time() if now is None else now
        rows = (
            self._conn()
            .execute(
                "SELECT parts, count, last_ts FROM usage WHERE connection = ? AND kind = 'table'",
                (connection,),
            )
            .fetchall()
        )
        rows.sort(key=lambda r: _score(r[1], r[2], now), reverse=True)
        return [tuple(json.loads(r[0])) for r in rows[:limit]]

    def needs_backfill(self, connection: str) -> bool:
        row = (
            self._conn()
            .execute("SELECT 1 FROM backfilled WHERE connection = ?", (connection,))
            .fetchone()
        )
        return row is None

    def mark_backfilled(self, connection: str) -> None:
        db = self._conn()
        db.execute("INSERT OR IGNORE INTO backfilled (connection) VALUES (?)", (connection,))
        db.commit()

    def forget(self, connection: str) -> None:
        db = self._conn()
        db.execute("DELETE FROM usage WHERE connection = ?", (connection,))
        db.execute("DELETE FROM backfilled WHERE connection = ?", (connection,))
        db.commit()

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None
