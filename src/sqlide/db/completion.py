"""Autocomplete candidates: a Context (what is typed) + MetaCache (what exists) + keywords."""

from __future__ import annotations

from dataclasses import dataclass

from sqlide.db.metadata import MetaCache, Namespace, Table, visible_namespaces
from sqlide.db.result import DbError
from sqlide.sql.context import Context
from sqlide.sql.keywords import functions, keywords
from sqlide.sql.snippets import qualified_name, quote_ident

MAX_CANDIDATES = 60
MAX_SCHEMAS = 8  # tables of at most this many chosen schemas are offered without a qualifier


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str  # what gets inserted (already quoted when needed)
    kind: str  # column | table | view | schema | keyword | function
    detail: str = ""
    match: str = ""  # what the typed prefix is compared with, when it differs from `text`


def _same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


async def _find_namespace(meta: MetaCache, name: str) -> Namespace | None:
    return next((n for n in await meta.namespaces() if _same(n.name, name)), None)


async def _find_catalog(meta: MetaCache, name: str) -> str | None:
    return next((c for c in await meta.catalogs() if _same(c, name)), None)


async def _find_schema(meta: MetaCache, catalog: str, name: str) -> Namespace | None:
    return next((n for n in await meta.schemas_of(catalog) if _same(n.name, name)), None)


async def _resolve(meta: MetaCache, ref_parts: tuple[str, ...]) -> Table | None:
    """Table named by `ref_parts`: (table,), (schema, table) or (catalog, schema, table)."""
    name = ref_parts[-1] if ref_parts else ""
    if not name:
        return None
    if len(ref_parts) >= 3:
        catalog = await _find_catalog(meta, ref_parts[-3])
        ns = await _find_schema(meta, catalog, ref_parts[-2]) if catalog else None
    elif len(ref_parts) == 2:
        ns = await _find_namespace(meta, ref_parts[-2])
    else:
        current = await meta.current_namespace()
        ns = await _find_namespace(meta, current)
    if ns is None:
        return None
    return next((t for t in await meta.tables(ns) if _same(t.name, name)), None)


async def _columns_of(meta: MetaCache, parts: tuple[str, ...], dialect: str) -> list[Candidate]:
    table = await _resolve(meta, parts)
    if table is None:
        return []
    return [
        Candidate(
            quote_ident(c.name, dialect), "column", c.type_name + (" · pk" if c.primary_key else "")
        )
        for c in await meta.columns(table)
    ]


def _table_candidates(tables: list[Table], dialect: str) -> list[Candidate]:
    return [
        Candidate(quote_ident(t.name, dialect), "view" if t.is_view else "table") for t in tables
    ]


def _match(word: str, prefix: str) -> bool:
    return word.lower().startswith(prefix.lower())


def _keyword_case(word: str, prefix: str) -> str:
    return word.lower() if prefix and prefix.islower() else word


async def candidates(
    ctx: Context,
    meta: MetaCache | None,
    dialect: str,
    selected: list[str] | None = None,
    catalogs: list[str] | None = None,
) -> list[Candidate]:
    """Ranked candidates for `ctx`. A metadata failure degrades to keywords only.

    `selected` are the schemas the user chose to show: their tables are offered too.
    The failure is kept in `meta.error` so the UI can tell the user why there are no tables.
    """
    found: list[Candidate] = []
    if meta is not None:
        try:
            found = await _from_metadata(ctx, meta, dialect, selected, catalogs)
            meta.error = None
        except DbError as e:
            meta.error = str(e).splitlines()[0] if str(e) else repr(e)
            found = []
    if ctx.kind != "qualified":
        found += [Candidate(_keyword_case(k, ctx.prefix), "keyword") for k in keywords(dialect)]
        if ctx.kind == "column":
            found += [
                Candidate(_keyword_case(f, ctx.prefix), "function") for f in functions(dialect)
            ]
    seen: set[tuple[str, str]] = set()
    out: list[Candidate] = []
    for c in found:
        key = (c.text.lower(), c.kind)
        if key in seen or not _match((c.match or c.text).strip('"`[]'), ctx.prefix):
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


async def _from_metadata(
    ctx: Context,
    meta: MetaCache,
    dialect: str,
    selected: list[str] | None,
    catalogs: list[str] | None,
) -> list[Candidate]:
    if ctx.kind == "qualified":
        return await _qualified(ctx, meta, dialect)
    out: list[Candidate] = []
    if ctx.kind == "table":
        spaces = await meta.namespaces()
        current = await meta.current_namespace()
        shown, _ = visible_namespaces(spaces, current, selected)
        home = await _find_namespace(meta, current)
        if home is not None and home not in shown:
            shown = [home, *shown]  # unqualified names resolve there whatever was chosen
        current_cat = await meta.current_catalog() if await meta.catalogs() else ""
        elsewhere = await _chosen_elsewhere(meta, selected, current_cat)
        for ns in [*shown, *elsewhere][:MAX_SCHEMAS]:
            at_home = _same(ns.name, current) and _same(ns.catalog, current_cat)
            for t in await meta.tables(ns):
                kind = "view" if t.is_view else "table"
                if at_home or not (ns.name or ns.catalog):
                    out.append(Candidate(quote_ident(t.name, dialect), kind))
                else:  # another schema or catalog: insert the name that works from here
                    here = ns.catalog if ns.catalog != current_cat else ""
                    text = qualified_name([here, ns.name, t.name], dialect)
                    detail = ".".join(p for p in (ns.catalog, ns.name) if p)
                    out.append(Candidate(text, kind, detail, match=t.name))
        names = spaces if selected is None else shown  # no choice yet: every schema name helps
        out += [Candidate(quote_ident(n.name, dialect), "schema") for n in names if n.name]
        if await meta.catalogs():  # three-level names: `catalog.schema.table`
            cats = await meta.catalogs() if catalogs is None else catalogs
            out += [Candidate(quote_ident(c, dialect), "catalog") for c in cats]
        return out
    # column context: columns of every table the statement mentions
    for ref in ctx.tables:
        out += await _columns_of(meta, ref.parts, dialect)
    return out


async def _chosen_elsewhere(
    meta: MetaCache, selected: list[str] | None, current_cat: str
) -> list[Namespace]:
    """Schemas the user chose in catalogs other than the working one (`catalog/schema`)."""
    out: list[Namespace] = []
    for key in selected or []:
        cat, _, name = key.partition("/")
        if not name or _same(cat, current_cat):
            continue
        found = await _find_catalog(meta, cat)
        ns = await _find_schema(meta, found, name) if found else None
        if ns is not None:
            out.append(ns)
    return out


async def _qualified(ctx: Context, meta: MetaCache, dialect: str) -> list[Candidate]:
    q = ctx.qualifier
    ref = next((t for t in ctx.tables if t.alias and _same(t.alias, q[-1])), None)
    if ref is not None:
        return await _columns_of(meta, ref.parts, dialect)
    if len(q) == 1:
        ns = await _find_namespace(meta, q[0])
        if ns is not None:
            return _table_candidates(await meta.tables(ns), dialect)
        catalog = await _find_catalog(meta, q[0])
        if catalog is not None:  # `catalog.` -> its schemas
            return [
                Candidate(quote_ident(n.name, dialect), "schema")
                for n in await meta.schemas_of(catalog)
            ]
    if len(q) == 2:
        catalog = await _find_catalog(meta, q[0])
        ns = await _find_schema(meta, catalog, q[1]) if catalog else None
        if ns is not None:  # `catalog.schema.` -> its tables
            return _table_candidates(await meta.tables(ns), dialect)
    # table-name qualifier: `users.` or `schema.users.`
    return await _columns_of(meta, q, dialect)
