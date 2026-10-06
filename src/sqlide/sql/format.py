"""SQL pretty-printing (via sqlglot) and line-comment toggling."""

from __future__ import annotations

import sqlglot
from sqlglot.errors import SqlglotError

from sqlide.sql.dialects import RULES
from sqlide.sql.splitter import split

_SQLGLOT = {"mssql": "tsql", "generic": None, "h2": None}


class FormatError(Exception):
    pass


def format_sql(sql: str, dialect: str = "generic") -> str:
    """Pretty-print one or more statements; the text is left alone if it cannot be parsed."""
    name = _SQLGLOT.get(dialect, dialect)
    parts = [s.text(sql) for s in split(sql, dialect if dialect in RULES else "generic")]
    try:
        out = [
            sqlglot.transpile(part, read=name, write=name, pretty=True)[0]
            for part in parts
            if part.strip()
        ]
    except SqlglotError as e:
        raise FormatError(str(e).splitlines()[0]) from e
    return ";\n\n".join(out)


def toggle_line_comments(lines: list[str]) -> list[str]:
    """Comment all lines, or uncomment them when every non-blank line is already commented."""
    body = [ln for ln in lines if ln.strip()]
    if not body:
        return lines
    if all(ln.lstrip().startswith("--") for ln in body):
        out = []
        for ln in lines:
            stripped = ln.lstrip()
            if stripped.startswith("--"):
                indent = ln[: len(ln) - len(stripped)]
                rest = stripped[2:]
                out.append(indent + (rest[1:] if rest.startswith(" ") else rest))
            else:
                out.append(ln)
        return out
    indent = min(len(ln) - len(ln.lstrip()) for ln in body)
    return [ln if not ln.strip() else ln[:indent] + "-- " + ln[indent:] for ln in lines]
