"""Application service: saved connections, drivers, passwords, sessions.

Everything the UI needs from the non-UI blocks, in one place. Holds no widgets.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable

from sqlide.config.connections import Connection, ConnectionStore
from sqlide.config.secrets import PasswordResolver
from sqlide.config.settings import Settings, load_settings
from sqlide.consoles import ConsoleStore
from sqlide.db.factory import create_session
from sqlide.db.session import DbSession
from sqlide.drivers.registry import DriverDef, DriverRegistry
from sqlide.jvm.runtime import ensure_jvm


class Workspace:
    def __init__(
        self,
        store: ConnectionStore | None = None,
        registry: DriverRegistry | None = None,
        resolver: PasswordResolver | None = None,
        settings: Settings | None = None,
        consoles: ConsoleStore | None = None,
    ) -> None:
        self.store = store or ConnectionStore()
        self.registry = registry or DriverRegistry()
        self.resolver = resolver or PasswordResolver()
        self.settings = settings or load_settings()
        self.consoles = consoles or ConsoleStore()

    # --- connections ---
    def connections(self) -> list[Connection]:
        return self.store.load()

    def save_connection(self, conn: Connection, replaces: str | None = None) -> None:
        if replaces and replaces != conn.name:
            self.store.remove(replaces)
        self.store.upsert(conn)

    def delete_connection(self, name: str) -> None:
        self.store.remove(name)
        self.resolver.forget(name)

    # --- drivers ---
    def driver(self, driver_id: str) -> DriverDef:
        return self.registry.get(driver_id)

    def driver_ready(self, conn: Connection) -> bool:
        return self.registry.is_installed(conn.driver)

    async def install_driver(
        self, driver_id: str, progress: Callable[[int, int | None], None] | None = None
    ) -> None:
        await asyncio.to_thread(self.registry.install, driver_id, None, None, progress)

    # --- sessions ---
    @staticmethod
    def needs_password_prompt(conn: Connection) -> bool:
        """No user means no credentials (sqlite, h2, duckdb): never ask."""
        return bool(conn.user)

    async def lookup_password(self, conn: Connection) -> str | None:
        return await asyncio.to_thread(self.resolver.lookup, conn)

    async def connect(self, conn: Connection, password: str | None) -> DbSession:
        await asyncio.to_thread(ensure_jvm)
        session = await asyncio.to_thread(create_session, conn, password or None, self.registry)
        try:
            await session.open()
        except BaseException:
            await session.close()
            raise
        return session
