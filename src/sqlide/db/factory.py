"""Glue: saved Connection + driver registry -> DbSession (not yet opened)."""

from __future__ import annotations

from sqlide.config.connections import Connection
from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry


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
        defn.dialect,
        conn.autocommit,
    )
