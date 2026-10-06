"""Small SQL generators for the UI: identifier quoting and "select from table" statements."""

from __future__ import annotations

import re

_SIMPLE = re.compile(r"^[A-Za-z_][A-Za-z0-9_$]*$")

# How an unquoted identifier is case-folded, per dialect. None: case is preserved/ignored.
_FOLD = {"postgres": str.lower, "oracle": str.upper, "generic": str.upper}
_QUOTES = {"mysql": ("`", "`"), "clickhouse": ("`", "`"), "mssql": ("[", "]")}


def quote_ident(name: str, dialect: str) -> str:
    """Quote `name` only when leaving it bare would change its meaning."""
    fold = _FOLD.get(dialect)
    if _SIMPLE.match(name) and (fold is None or fold(name) == name):
        return name
    left, right = _QUOTES.get(dialect, ('"', '"'))
    return left + name.replace(right, right * 2) + right


def qualified_name(parts: list[str], dialect: str) -> str:
    return ".".join(quote_ident(p, dialect) for p in parts if p)


def select_all(table: str, dialect: str, limit: int = 100) -> str:
    """`table` is already qualified/quoted."""
    if dialect == "mssql":
        return f"SELECT TOP {limit} * FROM {table}"
    if dialect == "oracle":
        return f"SELECT * FROM {table} FETCH FIRST {limit} ROWS ONLY"
    return f"SELECT * FROM {table} LIMIT {limit}"
