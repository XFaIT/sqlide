"""Lazy, cached database metadata (schemas, tables, columns) read through JDBC DatabaseMetaData.

Pure data + one class that needs a session; nothing here knows about the UI.
"""

from __future__ import annotations

import contextlib
import fnmatch
from dataclasses import dataclass
from typing import Any

import jpype

from sqlide.db.session import DbSession, _db_error

# Databases whose catalogs can all be read and queried through one connection, so the tree
# has three levels. (PostgreSQL's driver lists databases but reads only the connected one.)
THREE_LEVEL_URLS = ("jdbc:sqlserver:", "jdbc:databricks:", "jdbc:spark:", "jdbc:snowflake:")

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
    """A schema, or a catalog on databases that have no schemas (MySQL, ClickHouse).

    `catalog` is set for a schema inside a catalog when the connection has several catalogs
    (SQL Server, Databricks): names then have three parts.
    """

    name: str
    is_catalog: bool = False
    catalog: str = ""

    @property
    def key(self) -> str:
        """Stable id used in the saved choice: `schema`, or `catalog/schema` in three levels."""
        return f"{self.catalog}/{self.name}" if self.catalog else self.name


@dataclass(frozen=True)
class Table:
    namespace: str
    name: str
    kind: str  # driver-specific: TABLE, BASE TABLE, VIEW, ...
    is_catalog: bool = False
    catalog: str = ""

    @property
    def is_view(self) -> bool:
        return "VIEW" in self.kind.upper()

    @property
    def parts(self) -> list[str]:
        return [p for p in (self.catalog, self.namespace, self.name) if p]

    @property
    def qualified(self) -> str:
        return ".".join(self.parts)


@dataclass(frozen=True)
class Column:
    name: str
    type_name: str
    nullable: bool
    primary_key: bool = False


def visible_namespaces(
    spaces: list[Namespace], current: str, selected: list[str] | None
) -> tuple[list[Namespace], int]:
    """The namespaces the tree shows and how many it leaves out.

    `selected` is the user's choice (case-insensitive); None means nothing was chosen yet.
    Then a database with one user schema shows everything and one with several shows only the
    working schema until the user picks (the picker opens by itself, like in DataGrip).
    """
    if selected is not None:
        chosen = {n.lower() for n in selected}
        shown = [n for n in spaces if n.key.lower() in chosen]
    elif sum(1 for n in spaces if not is_system_namespace(n.name)) <= 1:
        shown = list(spaces)
    else:
        shown = [n for n in spaces if current and n.name.lower() == current.lower()]
    return shown, len(spaces) - len(shown)


def needs_choice(spaces: list[Namespace]) -> bool:
    """Several user schemas and no choice yet: the user should pick which ones to show."""
    return sum(1 for n in spaces if not is_system_namespace(n.name)) > 1


def table_matches(name: str, patterns: str) -> bool:
    """Comma-separated name filter: globs (`fact_*`) or plain substrings, case-insensitive."""
    pats = [p.strip().lower() for p in patterns.split(",") if p.strip()]
    if not pats:
        return True
    low = name.lower()
    return any(
        fnmatch.fnmatchcase(low, p if any(c in p for c in "*?[") else f"*{p}*") for p in pats
    )


def _scope(name: str, is_catalog: bool, catalog: str = "") -> tuple[str | None, str | None]:
    """(catalog, schema) arguments for DatabaseMetaData; "" means no filter at all."""
    if not name:
        return None, None
    if is_catalog:
        return name, None
    return (catalog or None), name


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
        self._catalogs: list[str] | None = None
        self._current_catalog: str | None = None
        self._catalog_schemas: dict[str, list[Namespace]] = {}
        self._tables: dict[str, list[Table]] = {}
        self._columns: dict[tuple[str, str, str], list[Column]] = {}
        self.error: str | None = None  # last metadata failure seen by autocomplete

    def use(self, session: DbSession) -> None:
        """Read from another session (a dedicated one) from now on; the cache stays."""
        self._s = session

    def refresh(self) -> None:
        self._namespaces = None
        self._current = None
        self._catalogs = None
        self._current_catalog = None
        self._catalog_schemas.clear()
        self._tables.clear()
        self._columns.clear()
        self.error = None

    # --- loading ---
    async def namespaces(self) -> list[Namespace]:
        """Schemas (or catalogs) of the working catalog; see `catalogs()` for the others."""
        if self._namespaces is None:
            if await self.catalogs():
                self._namespaces = await self.schemas_of(await self.current_catalog())
            else:
                self._namespaces = await self._s.call(self._load_namespaces)
        return self._namespaces

    async def catalogs(self) -> list[str]:
        """Catalog names when schemas live in several catalogs (three-level names), else []."""
        if self._catalogs is None:
            self._catalogs = await self._s.call(lambda c: self._load_catalogs(c, self._s.url))
        return self._catalogs

    @staticmethod
    def _load_catalogs(conn: Any, url: str) -> list[str]:
        if not url.lower().startswith(THREE_LEVEL_URLS):
            return []
        try:
            cats = [r[0] for r in _rows(conn.getMetaData().getCatalogs(), "TABLE_CAT")]
        except jpype.JException as e:
            raise _db_error(e) from e
        return sorted(cats, key=str.lower) if len(cats) > 1 else []

    async def current_catalog(self) -> str:
        if self._current_catalog is None:
            self._current_catalog = await self._s.call(self._load_current_catalog)
        return self._current_catalog

    @staticmethod
    def _load_current_catalog(conn: Any) -> str:
        try:
            value = conn.getCatalog()
        except jpype.JException:
            return ""
        return "" if value is None else str(value)

    async def schemas_of(self, catalog: str) -> list[Namespace]:
        if catalog not in self._catalog_schemas:
            self._catalog_schemas[catalog] = await self._s.call(
                lambda c: self._load_schemas_of(c, catalog)
            )
        return self._catalog_schemas[catalog]

    @staticmethod
    def _load_schemas_of(conn: Any, catalog: str) -> list[Namespace]:
        try:
            rs = conn.getMetaData().getSchemas(catalog, "%")
            names = [r[0] for r in _rows(rs, "TABLE_SCHEM") if r[0]]
        except jpype.JException as e:
            raise _db_error(e) from e
        return [Namespace(n, False, catalog) for n in sorted(names, key=str.lower)]

    @staticmethod
    def _load_namespaces(conn: Any) -> list[Namespace]:
        try:
            md = conn.getMetaData()
            schemas = [r[0] for r in _rows(md.getSchemas(), "TABLE_SCHEM")]
            if schemas:
                return [Namespace(s) for s in sorted(schemas, key=str.lower)]
            cats = [r[0] for r in _rows(md.getCatalogs(), "TABLE_CAT")]
            if cats:
                return [Namespace(c, True) for c in sorted(cats, key=str.lower)]
            return [Namespace("")]  # SQLite & co: no schemas at all, tables are just there
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
        if ns.key not in self._tables:
            self._tables[ns.key] = await self._s.call(lambda c: self._load_tables(c, ns))
        return self._tables[ns.key]

    @staticmethod
    def _load_tables(conn: Any, ns: Namespace) -> list[Table]:
        try:
            md = conn.getMetaData()
            cat, sch = _scope(ns.name, ns.is_catalog, ns.catalog)
            types: Any = jpype.JArray(jpype.JString)
            rs = md.getTables(cat, sch, "%", types(TABLE_TYPES))
            rows = _rows(rs, "TABLE_NAME", "TABLE_TYPE")
        except jpype.JException as e:
            raise _db_error(e) from e
        rows.sort(key=lambda r: (r[0] or "").lower())
        return [Table(ns.name, n or "", t or "TABLE", ns.is_catalog, ns.catalog) for n, t in rows]

    async def columns(self, table: Table) -> list[Column]:
        key = (table.catalog, table.namespace, table.name)
        if key not in self._columns:
            self._columns[key] = await self._s.call(lambda c: self._load_columns(c, table))
        return self._columns[key]

    @staticmethod
    def _load_columns(conn: Any, t: Table) -> list[Column]:
        try:
            md = conn.getMetaData()
            cat, sch = _scope(t.namespace, t.is_catalog, t.catalog)
            pks = {r[0] for r in _rows(md.getPrimaryKeys(cat, sch, t.name), "COLUMN_NAME")}
            rows = _rows(
                md.getColumns(cat, sch, t.name, "%"), "COLUMN_NAME", "TYPE_NAME", "IS_NULLABLE"
            )
        except jpype.JException as e:
            raise _db_error(e) from e
        return [Column(n or "", ty or "", nl != "NO", n in pks) for n, ty, nl in rows]
