"""Glue: saved Connection + driver registry -> DbSession (not yet opened)."""

from __future__ import annotations

from sqlide.config.connections import Connection
from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry
from sqlide.sql.dialects import dialect_for


def create_session(
    conn: Connection, password: str | None, registry: DriverRegistry | None = None
) -> DbSession:
    """Blocking (may start the JVM, ~1s): call from a worker thread in the UI."""
    registry = registry or DriverRegistry()
    defn = registry.get(conn.driver)
    loaded = load_driver(defn, registry.jar_paths(conn.driver))
    return DbSession(
        loaded,
        conn.url,
        conn.user,
        password,
        conn.properties,
        dialect_for(conn.url, defn.dialect),
        conn.autocommit,
    )


_PRIVATE_MARKERS = (":mem:", ":memory:", "mode=memory", "jdbc:derby:memory", "jdbc:duckdb:")


def is_private_database(url: str) -> bool:
    """True when a second connection would not see this connection's data (in-memory DBs)."""
    low = url.lower()
    if low.startswith("jdbc:duckdb:"):
        return low in ("jdbc:duckdb:", "jdbc:duckdb::memory:") or ":memory:" in low
    return any(m in low for m in _PRIVATE_MARKERS)
