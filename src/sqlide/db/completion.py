"""Autocomplete candidates: a Context (what is typed) + MetaCache (what exists) + keywords."""

from __future__ import annotations

from dataclasses import dataclass

from sqlide.db.metadata import MetaCache, Namespace, Table
from sqlide.db.result import DbError
from sqlide.sql.context import Context
from sqlide.sql.keywords import functions, keywords
from sqlide.sql.snippets import quote_ident

MAX_CANDIDATES = 60


@dataclass(frozen=True, slots=True)
class Candidate:
    text: str  # what gets inserted (already quoted when needed)
    kind: str  # column | table | view | schema | keyword | function
    detail: str = ""


def _same(a: str, b: str) -> bool:
    return a.lower() == b.lower()


async def _find_namespace(meta: MetaCache, name: str) -> Namespace | None:
    return next((n for n in await meta.namespaces() if _same(n.name, name)), None)


async def _resolve(meta: MetaCache, ref_parts: tuple[str, ...]) -> Table | None:
    """Table named by `ref_parts` ((table,) or (schema, table)) among the cached metadata."""
    name = ref_parts[-1] if ref_parts else ""
    if not name:
        return None
    if len(ref_parts) >= 2:
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


async def candidates(ctx: Context, meta: MetaCache | None, dialect: str) -> list[Candidate]:
    """Ranked candidates for `ctx`. A metadata failure degrades to keywords only."""
    found: list[Candidate] = []
    if meta is not None:
        try:
            found = await _from_metadata(ctx, meta, dialect)
        except DbError:
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
        if key in seen or not _match(c.text.strip('"`[]'), ctx.prefix):
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= MAX_CANDIDATES:
            break
    return out


async def _from_metadata(ctx: Context, meta: MetaCache, dialect: str) -> list[Candidate]:
    if ctx.kind == "qualified":
        return await _qualified(ctx, meta, dialect)
    spaces = await meta.namespaces()
    out: list[Candidate] = []
    if ctx.kind == "table":
        current = await meta.current_namespace()
        ns = await _find_namespace(meta, current)
        if ns is not None:
            out += _table_candidates(await meta.tables(ns), dialect)
        out += [Candidate(quote_ident(n.name, dialect), "schema") for n in spaces]
        return out
    # column context: columns of every table the statement mentions, then table names
    for ref in ctx.tables:
        out += await _columns_of(meta, ref.parts, dialect)
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
    # table-name qualifier: `users.` or `schema.users.`
    return await _columns_of(meta, q, dialect)
