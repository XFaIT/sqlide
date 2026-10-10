"""What is the user typing? Pure analysis of the statement around the cursor.

No metadata, no UI: it only says what *kind* of name is expected and which tables the
statement mentions, so a provider can fetch candidates.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlide.sql.dialects import RULES, Rules
from sqlide.sql.lexer import (
    BLOCK_COMMENT,
    LINE_COMMENT,
    LPAREN,
    QIDENT,
    RPAREN,
    SEMI,
    STRING,
    WORD,
    WS,
    Token,
    tokenize,
)

TABLE_KEYWORDS = frozenset({"FROM", "JOIN", "INTO", "UPDATE", "TABLE", "DESCRIBE", "TRUNCATE"})
CLAUSE_KEYWORDS = TABLE_KEYWORDS | {
    "SELECT", "WHERE", "ON", "GROUP", "ORDER", "HAVING", "SET", "VALUES", "BY", "AND", "OR",
    "WHEN", "THEN", "ELSE", "USING", "RETURNING",
}  # fmt: skip
# a word that follows a table reference but is not its alias
NOT_ALIAS = frozenset(
    {
        "WHERE", "GROUP", "ORDER", "HAVING", "LIMIT", "OFFSET", "UNION", "INTERSECT", "EXCEPT",
        "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "OUTER", "NATURAL", "ON", "USING",
        "SET", "VALUES", "SELECT", "RETURNING", "FETCH", "WINDOW", "FOR", "LATERAL", "FINAL",
        "SAMPLE", "PREWHERE", "SETTINGS", "FORMAT", "AS",
    }
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class TableRef:
    parts: tuple[str, ...]  # ("schema", "table") or ("table",)
    alias: str = ""

    @property
    def name(self) -> str:
        return self.parts[-1]


@dataclass(slots=True)
class Context:
    # "table": a table name is expected; "column": a column/keyword; "qualified": after "x."
    kind: str
    prefix: str  # the partial word before the cursor ("" when none)
    qualifier: tuple[str, ...] = ()  # names before the last dot
    tables: list[TableRef] = field(default_factory=list)
    lead: int = 0  # characters before the prefix that the completion also replaces (open quote)

    @property
    def replace_len(self) -> int:
        return len(self.prefix) + self.lead


_CLOSERS = {'"': '"', "`": "`", "[": "]"}


def _unquote(s: str) -> str:
    if len(s) >= 2 and s[0] in '"`[' and s[-1] in '"`]':
        close = s[-1]
        return s[1:-1].replace(close * 2, close)  # `a``b` -> a`b
    return s


def _open_quote(text: str, offset: int, toks: list[Token]) -> int | None:
    """Start of an identifier quote left open before the cursor (`dbt-an|), same line only."""
    for t in toks:
        if t.kind != QIDENT or not t.start < offset <= t.end:
            continue
        body = text[t.start : t.end]
        closed = len(body) >= 2 and body[-1] == _CLOSERS[body[0]] and t.end <= len(text)
        if not closed and "\n" not in text[t.start : offset]:
            return t.start
    return None


def _statement_bounds(text: str, offset: int, toks: list[Token]) -> tuple[int, int]:
    """Cheap bounds: nearest ';' tokens around the cursor (blank-line splitting is ignored)."""
    start, end = 0, len(text)
    for t in toks:
        if t.kind == SEMI:
            if t.end <= offset:
                start = t.end
            elif t.start >= offset:
                end = t.start
                break
    return start, end


def _significant(toks: list[Token], lo: int, hi: int) -> list[Token]:
    skip = {WS, LINE_COMMENT, BLOCK_COMMENT}
    return [t for t in toks if t.start >= lo and t.end <= hi and t.kind not in skip]


def _table_refs(text: str, toks: list[Token]) -> list[TableRef]:
    refs: list[TableRef] = []
    i, n = 0, len(toks)
    while i < n:
        t = toks[i]
        if t.kind == WORD and text[t.start : t.end].upper() in {"FROM", "JOIN", "UPDATE", "INTO"}:
            i += 1
            while i < n:
                ref, i = _read_ref(text, toks, i)
                if ref is None:
                    break
                refs.append(ref)
                if i < n and text[toks[i].start : toks[i].end] == ",":
                    i += 1
                    continue
                break
        else:
            i += 1
    return refs


def _read_ref(text: str, toks: list[Token], i: int) -> tuple[TableRef | None, int]:
    n = len(toks)
    parts: list[str] = []
    while i < n and toks[i].kind in (WORD, QIDENT):
        parts.append(_unquote(text[toks[i].start : toks[i].end]))
        if i + 1 < n and text[toks[i + 1].start : toks[i + 1].end] == "." and i + 2 < n:
            i += 2
        else:
            i += 1
            break
    if not parts:
        return None, i
    alias = ""
    if i < n and toks[i].kind == WORD and text[toks[i].start : toks[i].end].upper() == "AS":
        i += 1
    if i < n and toks[i].kind in (WORD, QIDENT):
        word = text[toks[i].start : toks[i].end]
        if toks[i].kind == QIDENT or word.upper() not in NOT_ALIAS:
            alias = _unquote(word)
            i += 1
    return TableRef(tuple(parts), alias), i


def analyze(text: str, offset: int, dialect: str = "generic") -> Context | None:
    """Context at `offset`, or None where completion makes no sense (strings, comments)."""
    rules: Rules = RULES.get(dialect, RULES["generic"])
    toks = tokenize(text, rules)
    for t in toks:
        if t.kind not in (STRING, LINE_COMMENT, BLOCK_COMMENT) or not t.start < offset <= t.end:
            continue
        closed = {
            STRING: text[t.start : t.end].endswith("'") and t.end - t.start >= 2,
            BLOCK_COMMENT: text[t.start : t.end].endswith("*/") and t.end - t.start >= 4,
            LINE_COMMENT: False,  # a line comment runs to the newline, cursor at its end is inside
        }[t.kind]
        if offset < t.end or not closed:
            return None
    lo, hi = _statement_bounds(text, offset, toks)
    stmt = _significant(toks, lo, hi)

    # partial word under the cursor; inside an open `quote it is everything after the quote
    quote = _open_quote(text, offset, toks)
    if quote is not None:
        p = quote + 1
    else:
        p = offset
        while p > 0 and (text[p - 1].isalnum() or text[p - 1] in "_$"):
            p -= 1
    prefix = text[p:offset]
    lead = 1 if quote is not None else 0

    # qualifier: name(.name)* followed by a dot, directly before the prefix (or open quote)
    qual: list[str] = []
    q = p - lead
    while q > 0 and text[q - 1] == ".":
        q -= 1
        end = q
        if q > 0 and text[q - 1] in '"`]':
            close = text[q - 1]
            opener = {'"': '"', "`": "`", "]": "["}[close]
            start = text.rfind(opener, 0, q - 1)
            if start == -1:
                break
            qual.insert(0, text[start + 1 : q - 1])
            q = start
        else:
            while q > 0 and (
                text[q - 1].isalnum()
                or text[q - 1] in "_$"
                or (text[q - 1] == "-" and q > 1 and text[q - 2].isalnum())  # dbt-analytics.
            ):
                q -= 1
            if q == end:
                break
            qual.insert(0, text[q:end])
    refs = _table_refs(text, stmt)
    if qual:
        return Context("qualified", prefix, tuple(qual), refs, lead)

    # nearest clause keyword before the word being typed (ignoring closed sub-selects)
    kind = "column"
    depth = 0
    for t in reversed([t for t in stmt if t.end <= p]):
        if t.kind == RPAREN:
            depth += 1
        elif t.kind == LPAREN:
            if depth == 0:
                continue
            depth -= 1
        elif t.kind == WORD and depth == 0:
            word = text[t.start : t.end].upper()
            if word in CLAUSE_KEYWORDS:
                kind = "table" if word in TABLE_KEYWORDS else "column"
                break
    return Context(kind, prefix, (), refs, lead)
