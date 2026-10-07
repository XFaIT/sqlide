"""One JDBC connection = one DbSession.

JDBC connections are not thread-safe, so every JDBC call of a session runs on that
session's own single worker thread. The UI only awaits; cancel() may be called from
any thread (Statement.cancel is the one call JDBC allows concurrently).
"""

from __future__ import annotations

import asyncio
import contextlib
import threading
import time
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from typing import Any, TypeVar, cast

import jpype

from sqlide.db.result import Column, DbError, Execution, ResultItem
from sqlide.db.types import make_converter
from sqlide.drivers.loader import LoadedDriver

T = TypeVar("T")

DEFAULT_PAGE = 500


def _db_error(e: Exception, cancelled: bool = False) -> DbError:
    if cancelled:
        return DbError("Cancelled by user")
    if isinstance(e, jpype.JException):
        state = getattr(e, "getSQLState", lambda: "")() or ""
        code = getattr(e, "getErrorCode", lambda: 0)()
        return DbError(str(e.getMessage() or e), str(state), int(code))
    return DbError(str(e))


class _Cursor:
    """Open JDBC ResultSet; satisfies result.RowSource."""

    def __init__(self, session: DbSession, rs: Any, stmt: Any, convs: list, pending: bool) -> None:
        self._s, self._rs, self._stmt, self._convs = session, rs, stmt, convs
        self._pending = pending  # rs is already positioned on an unread row
        self.closed = False
        self.owns_stmt = False  # True once handed to the caller; before that execute() owns it

    def _read(self, n: int) -> tuple[list[tuple], bool]:
        if self.closed:
            raise DbError("Cursor is closed (another query ran). Re-run to load more rows.")
        rows: list[tuple] = []
        try:
            while len(rows) < n:
                if self._pending:
                    self._pending = False
                elif not self._rs.next():
                    self._close_sync()
                    return rows, True
                rows.append(tuple(c(self._rs) for c in self._convs))
            if self._rs.next():
                self._pending = True
                return rows, False
            self._close_sync()
            return rows, True
        except jpype.JException as e:
            self._close_sync()
            raise _db_error(e, self._s._cancelled) from e

    def _close_sync(self) -> None:
        if self.closed:
            return
        self.closed = True
        for o in (self._rs, self._stmt) if self.owns_stmt else (self._rs,):
            with contextlib.suppress(jpype.JException):
                o.close()
        self._s._cursors.discard(self)
        if self.owns_stmt:
            self._s._leave_paging_tx()

    async def fetch_more(self, n: int) -> tuple[list[tuple], bool]:
        return await self._s.call(lambda _c: self._read(n))

    async def close(self) -> None:
        if self._s._closed:  # the session already closed every cursor
            return
        await self._s.call(lambda _c: self._close_sync())


class DbSession:
    def __init__(
        self,
        loaded: LoadedDriver,
        url: str,
        user: str = "",
        password: str | None = None,
        properties: dict[str, str] | None = None,
        dialect: str = "generic",
        autocommit: bool = True,
    ) -> None:
        self._loaded, self._url, self._dialect = loaded, url, dialect
        self._props = dict(properties or {})
        if user:
            self._props["user"] = user
        if password is not None:
            self._props["password"] = password
        self._want_autocommit = autocommit
        self._conn: Any = None
        self._closed = False
        self._pool = ThreadPoolExecutor(1, "sqlide-jdbc", initializer=self._init_thread)
        self._lock = threading.Lock()
        self._stmt: Any = None
        self._cancelled = False
        self._cursors: set[_Cursor] = set()
        self._paging_tx = False  # we turned autocommit off only to get server-side cursors
        self.pending_tx = False  # manual mode: statements since last commit/rollback
        self.product = ""

    @property
    def url(self) -> str:
        return self._url

    # --- plumbing ---
    def _init_thread(self) -> None:
        # drivers using ServiceLoader (ClickHouse) look classes up via the context loader
        jpype.JClass("java.lang.Thread").currentThread().setContextClassLoader(self._loaded.loader)

    async def call(self, fn: Callable[[Any], T]) -> T:
        """Run fn(java_connection) on the session thread. Use for metadata and misc JDBC."""
        if self._closed:
            raise DbError("Connection is closed")
        loop = asyncio.get_running_loop()
        try:
            return await loop.run_in_executor(self._pool, lambda: fn(self._conn))
        except RuntimeError as e:  # closed between the check and the submit
            if self._closed or "after shutdown" in str(e):
                raise DbError("Connection is closed") from e
            raise

    # --- lifecycle ---
    async def open(self) -> None:
        def connect(_: Any) -> None:
            props = jpype.JClass("java.util.Properties")()
            for k, v in self._props.items():
                props.setProperty(k, v)
            try:
                conn = self._loaded.driver.connect(self._url, props)
                if conn is None:
                    raise DbError(f"Driver does not accept URL: {self._url}")
                conn.setAutoCommit(self._want_autocommit)
                md = conn.getMetaData()
                self.product = f"{md.getDatabaseProductName()} {md.getDatabaseProductVersion()}"
            except jpype.JException as e:
                raise _db_error(e) from e
            self._conn = conn

        await self.call(connect)

    async def close(self) -> None:
        if self._closed:
            return
        if self._conn is None:
            self._closed = True
            self._pool.shutdown(wait=False)
            return
        self.cancel()

        def shut(conn: Any) -> None:
            for c in list(self._cursors):
                c._close_sync()
            if self.pending_tx:  # some drivers (Oracle) would commit on close
                with contextlib.suppress(jpype.JException):
                    conn.rollback()
            with contextlib.suppress(jpype.JException):
                conn.close()

        try:
            await self.call(shut)
        finally:
            self._closed = True
            self._conn = None
            self._pool.shutdown(wait=False)

    @property
    def connected(self) -> bool:
        return self._conn is not None

    # --- execution ---
    async def execute(self, sql: str, page_size: int = DEFAULT_PAGE) -> Execution:
        return await self.call(lambda _c: self._execute_sync(sql, page_size))

    async def stream(
        self,
        sql: str,
        consumer: Callable[[list[Column], Iterator[tuple]], T],
        page_size: int = 2000,
    ) -> T:
        """Run `sql`, hand its first result set to `consumer` as a lazy row iterator.

        `consumer` runs on the session thread, so it may block (write a file). Pages are
        fetched on demand: memory stays flat for any result size.
        """
        return await self.call(lambda _c: self._stream_sync(sql, page_size, consumer))

    def _stream_sync(
        self, sql: str, page_size: int, consumer: Callable[[list[Column], Iterator[tuple]], T]
    ) -> T:
        ex = self._execute_sync(sql, page_size)
        item = next((i for i in ex.items if i.has_rows), None)
        if item is None:
            raise DbError("The statement did not return a result set")

        cur = cast("_Cursor | None", item.cursor)

        def rows() -> Iterator[tuple]:
            yield from item.rows
            while cur is not None and not cur.closed:
                page, done = cur._read(page_size)
                yield from page
                if done:
                    break

        try:
            return consumer(item.columns, rows())
        finally:
            if cur is not None:
                cur._close_sync()

    def cancel(self) -> None:
        """Thread-safe. Aborts the running statement, if any."""
        with self._lock:
            stmt = self._stmt
        if stmt is not None:
            self._cancelled = True
            with contextlib.suppress(jpype.JException):
                stmt.cancel()

    def _execute_sync(self, sql: str, page_size: int) -> Execution:
        for c in list(self._cursors):  # one live result per session, see module docs
            c._close_sync()
        self._cancelled = False
        self._enter_paging_tx()
        t0 = time.perf_counter()
        stmt = self._conn.createStatement()
        keep_open = False
        try:
            stmt.setFetchSize(page_size)
            with self._lock:
                self._stmt = stmt
            items: list[ResultItem] = []
            has_rs = bool(stmt.execute(sql))
            while True:
                if has_rs:
                    item, more = self._read_first_page(stmt.getResultSet(), stmt, page_size)
                    items.append(item)
                    if more:  # cursor owns the statement now; further results are not reachable
                        keep_open = True
                        break
                else:
                    n = int(stmt.getUpdateCount())
                    if n == -1:
                        break
                    items.append(ResultItem(update_count=n))
                has_rs = bool(stmt.getMoreResults())
            warnings = self._warnings(stmt)
            if not self._want_autocommit:
                self.pending_tx = True
            return Execution(sql, items, warnings, time.perf_counter() - t0)
        except jpype.JException as e:
            err = _db_error(e, self._cancelled)
            keep_open = False
            self._rollback_paging_tx()
            raise err from e
        finally:
            with self._lock:
                self._stmt = None
            if not keep_open:
                with contextlib.suppress(jpype.JException):
                    stmt.close()
                self._leave_paging_tx()

    def _read_first_page(self, rs: Any, stmt: Any, page_size: int) -> tuple[ResultItem, bool]:
        md = rs.getMetaData()
        n = int(md.getColumnCount())
        cols = [
            Column(
                str(md.getColumnLabel(i)), str(md.getColumnTypeName(i)), int(md.getColumnType(i))
            )
            for i in range(1, n + 1)
        ]
        convs = [make_converter(i, c.jdbc_type) for i, c in zip(range(1, n + 1), cols, strict=True)]
        cur = _Cursor(self, rs, stmt, convs, pending=False)
        rows, done = cur._read(page_size)
        item = ResultItem(columns=cols, rows=rows)
        if done:
            return item, False
        cur.owns_stmt = True
        self._cursors.add(cur)
        item.cursor = cur
        return item, True

    @staticmethod
    def _warnings(stmt: Any) -> list[str]:
        out, w = [], stmt.getWarnings()
        while w is not None:
            out.append(str(w.getMessage()))
            w = w.getNextWarning()
        return out

    # --- postgres: fetchSize is ignored in autocommit mode, so page inside a transaction ---
    def _enter_paging_tx(self) -> None:
        if self._dialect == "postgres" and self._want_autocommit and not self._paging_tx:
            self._conn.setAutoCommit(False)
            self._paging_tx = True

    def _leave_paging_tx(self) -> None:
        if self._paging_tx and not self._cursors and self._conn is not None:
            self._paging_tx = False
            with contextlib.suppress(jpype.JException):
                self._conn.commit()
                self._conn.setAutoCommit(True)

    def _rollback_paging_tx(self) -> None:
        if self._paging_tx:
            self._paging_tx = False
            with contextlib.suppress(jpype.JException):
                self._conn.rollback()
                self._conn.setAutoCommit(True)

    # --- transactions ---
    async def set_autocommit(self, on: bool) -> None:
        def f(conn: Any) -> None:
            try:
                conn.setAutoCommit(on)
            except jpype.JException as e:
                raise _db_error(e) from e
            self._want_autocommit = on
            self.pending_tx = False

        await self.call(f)

    async def commit(self) -> None:
        await self._finish_tx("commit")

    async def rollback(self) -> None:
        await self._finish_tx("rollback")

    async def _finish_tx(self, how: str) -> None:
        def f(conn: Any) -> None:
            try:
                getattr(conn, how)()
            except jpype.JException as e:
                raise _db_error(e) from e
            self.pending_tx = False

        await self.call(f)

    @property
    def autocommit(self) -> bool:
        return self._want_autocommit
