"""Lazy, cached database metadata (schemas, tables, columns) read through JDBC DatabaseMetaData.

Pure data + one class that needs a session; nothing here knows about the UI.
"""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import Any

import jpype

from sqlide.db.session import DbSession, _db_error

TABLE_TYPES = ["TABLE", "VIEW", "MATERIALIZED VIEW", "SYSTEM TABLE", "FOREIGN TABLE"]


_SYSTEM = {
    "information_schema", "pg_catalog", "pg_toast", "sys", "mysql", "performance_schema",
    "system", "sysibm", "sysibmadm", "syscat", "sysstat", "ctxsys", "xdb", "mdsys",
    "outln", "dbsnmp", "appqossys", "audsys", "gsmadmin_internal", "lbacsys", "ordsys",
    "wmsys", "dvsys", "olapsys", "ojvmsys", "remote_scheduler_agent", "guest",
}  # fmt: skip


def is_system_namespace(name: str) -> bool:
    low = name.lower()
    return low in _SYSTEM or low.startswith(("pg_temp", "pg_toast"))


@dataclass(frozen=True)
class Namespace:
    """A schema, or a catalog on databases that have no schemas (MySQL, ClickHouse)."""

    name: str
    is_catalog: bool = False


@dataclass(frozen=True)
class Table:
    namespace: str
    name: str
    kind: str  # driver-specific: TABLE, BASE TABLE, VIEW, ...
    is_catalog: bool = False

    @property
    def is_view(self) -> bool:
        return "VIEW" in self.kind.upper()

    @property
    def qualified(self) -> str:
        return f"{self.namespace}.{self.name}" if self.namespace else self.name


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str
    nullable: bool
    primary_key: bool = False


def _rows(rs: Any, *cols: str) -> list[tuple[Any, ...]]:
    out = []
    try:
        while rs.next():
            out.append(tuple(None if (v := rs.getString(c)) is None else str(v) for c in cols))
    finally:
        with contextlib.suppress(jpype.JException):
            rs.close()
    return out


class MetaCache:
    """Per-session cache. Every getter loads once; `refresh()` drops it."""

    def __init__(self, session: DbSession) -> None:
        self._s = session
        self._namespaces: list[Namespace] | None = None
        self._current: str | None = None
        self._tables: dict[str, list[Table]] = {}
        self._columns: dict[tuple[str, str], list[Column]] = {}

    def refresh(self) -> None:
        self._namespaces = None
        self._current = None
        self._tables.clear()
        self._columns.clear()

    # --- loading ---
    async def namespaces(self) -> list[Namespace]:
        if self._namespaces is None:
            self._namespaces = await self._s.call(self._load_namespaces)
        return self._namespaces

    @staticmethod
    def _load_namespaces(conn: Any) -> list[Namespace]:
        try:
            md = conn.getMetaData()
            schemas = [r[0] for r in _rows(md.getSchemas(), "TABLE_SCHEM")]
            if schemas:
                return [Namespace(s) for s in sorted(schemas, key=str.lower)]
            cats = [r[0] for r in _rows(md.getCatalogs(), "TABLE_CAT")]
            return [Namespace(c, True) for c in sorted(cats, key=str.lower)]
        except jpype.JException as e:
            raise _db_error(e) from e

    async def current_namespace(self) -> str:
        """The schema (or catalog) unqualified names resolve to; "" when unknown."""
        if self._current is None:
            self._current = await self._s.call(self._load_current)
        return self._current

    @staticmethod
    def _load_current(conn: Any) -> str:
        for getter in (conn.getSchema, conn.getCatalog):
            try:
                value = getter()
            except jpype.JException:
                continue
            if value is not None:
                return str(value)
        return ""

    async def tables(self, ns: Namespace) -> list[Table]:
        if ns.name not in self._tables:
            self._tables[ns.name] = await self._s.call(lambda c: self._load_tables(c, ns))
        return self._tables[ns.name]

    @staticmethod
    def _load_tables(conn: Any, ns: Namespace) -> list[Table]:
        try:
            md = conn.getMetaData()
            cat, sch = (ns.name, None) if ns.is_catalog else (None, ns.name)
            types: Any = jpype.JArray(jpype.JString)
            rs = md.getTables(cat, sch, "%", types(TABLE_TYPES))
            rows = _rows(rs, "TABLE_NAME", "TABLE_TYPE")
        except jpype.JException as e:
            raise _db_error(e) from e
        rows.sort(key=lambda r: (r[0] or "").lower())
        return [Table(ns.name, n or "", t or "TABLE", ns.is_catalog) for n, t in rows]

    async def columns(self, table: Table) -> list[Column]:
        key = (table.namespace, table.name)
        if key not in self._columns:
            self._columns[key] = await self._s.call(lambda c: self._load_columns(c, table))
        return self._columns[key]

    @staticmethod
    def _load_columns(conn: Any, t: Table) -> list[Column]:
        try:
            md = conn.getMetaData()
            cat, sch = (t.namespace, None) if t.is_catalog else (None, t.namespace)
            pks = {r[0] for r in _rows(md.getPrimaryKeys(cat, sch, t.name), "COLUMN_NAME")}
            rows = _rows(
                md.getColumns(cat, sch, t.name, "%"), "COLUMN_NAME", "TYPE_NAME", "IS_NULLABLE"
            )
        except jpype.JException as e:
            raise _db_error(e) from e
        return [Column(n or "", ty or "", nl != "NO", n in pks) for n, ty, nl in rows]
