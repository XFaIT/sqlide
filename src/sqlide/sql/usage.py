"""Which tables and columns does a statement use? Pure lexical analysis, no metadata.

Feeds the usage counters behind autocomplete ranking and the "Recent" tables. Columns are
only counted when the table is certain: `alias.col`, or any column of a one-table statement.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlide.sql.context import TableRef, _table_refs, _unquote
from sqlide.sql.dialects import rules_for
from sqlide.sql.keywords import functions, keywords
from sqlide.sql.lexer import (
    BLOCK_COMMENT,
    LINE_COMMENT,
    LPAREN,
    PUNCT,
    QIDENT,
    WORD,
    WS,
    Token,
    tokenize,
)


@dataclass(frozen=True, slots=True)
class Use:
    kind: str  # "table" | "column"
    parts: tuple[str, ...]  # table: ([schema,] table); column: ([schema,] table, column)

    @property
    def key(self) -> str:
        return f"{self.kind}:" + ".".join(p.lower() for p in self.parts)


def _ctes(text: str, sig: list[Token]) -> set[str]:
    """Names introduced by `WITH name AS (` / `, name AS (`: they are not real tables."""
    out: set[str] = set()
    for i in range(1, len(sig) - 2):
        if sig[i].kind not in (WORD, QIDENT) or sig[i + 2].kind != LPAREN:
            continue
        if text[sig[i + 1].start : sig[i + 1].end].upper() != "AS":
            continue
        before = text[sig[i - 1].start : sig[i - 1].end].upper()
        if before in ("WITH", ",", "RECURSIVE"):
            out.add(_unquote(text[sig[i].start : sig[i].end]).lower())
    return out


def extract(sql: str, dialect: str = "generic") -> list[Use]:
    text = sql
    toks = [
        t
        for t in tokenize(text, rules_for(dialect))
        if t.kind not in (WS, LINE_COMMENT, BLOCK_COMMENT)
    ]
    ctes = _ctes(text, toks)
    refs: list[TableRef] = [r for r in _table_refs(text, toks) if r.parts[-1].lower() not in ctes]
    uses: dict[str, Use] = {}

    def add(use: Use) -> None:
        uses.setdefault(use.key, use)

    for r in refs:
        add(Use("table", r.parts[-2:]))
    by_name: dict[str, TableRef] = {}
    for r in refs:
        by_name[r.name.lower()] = r
        if r.alias:
            by_name[r.alias.lower()] = r
    known = {w.lower() for w in (*keywords(dialect), *functions(dialect))}
    skip = set(by_name) | ctes

    def word(i: int) -> str:
        return _unquote(text[toks[i].start : toks[i].end])

    n = len(toks)
    for i, t in enumerate(toks):
        if t.kind not in (WORD, QIDENT):
            continue
        raw = word(i)
        low = raw.lower()
        after = text[toks[i + 1].start : toks[i + 1].end] if i + 1 < n else ""
        before = text[toks[i - 1].start : toks[i - 1].end] if i else ""
        if after == "(" or before == ".":
            continue  # a function call, or the tail of a longer dotted name
        if after == ".":
            if i + 2 < n and toks[i + 2].kind in (WORD, QIDENT):
                tail = text[toks[i + 3].start : toks[i + 3].end] if i + 3 < n else ""
                ref = by_name.get(low)
                if ref is not None and tail != ".":  # alias.col (or table.col)
                    add(Use("column", (*ref.parts[-2:], word(i + 2))))
            continue
        if t.kind == WORD and (low in known or raw[0].isdigit() or raw.startswith(("@", "#"))):
            continue
        if low in skip or before.upper() == "AS" or toks[i].kind == PUNCT:
            continue
        if len(refs) == 1 and not ctes:  # with a CTE the bare columns may belong to it
            add(Use("column", (*refs[0].parts[-2:], raw)))
    return list(uses.values())
