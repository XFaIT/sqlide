"""Split a script into statement spans and find the statement under the cursor.

Spans cover the statement body only: leading/trailing whitespace and comments are
excluded, and the terminator ';' is excluded too, except for procedural blocks where
it is part of the statement (Oracle needs `END;`).
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

from sqlide.sql.dialects import BlockRules, Rules, rules_for
from sqlide.sql.lexer import (
    BLOCK_COMMENT,
    LINE_COMMENT,
    LPAREN,
    PUNCT,
    QIDENT,
    RPAREN,
    SEMI,
    STRING,
    WORD,
    WS,
    Token,
    tokenize,
)  # fmt: skip

_END_CLOSERS = frozenset({"IF", "LOOP", "CASE", "WHILE", "REPEAT", "FOR", "TRY", "CATCH"})
_STMT_START = frozenset({"", ";", "THEN", "ELSE", "BEGIN", "LOOP", "DO", "REPEAT", ":"})
_NOT_ROUTINE = frozenset(
    {"TABLE", "VIEW", "INDEX", "SEQUENCE", "SCHEMA", "DATABASE", "USER", "ROLE", "SYNONYM",
     "DOMAIN", "EXTENSION", "LANGUAGE", "CAST", "RULE", "POLICY", "STATISTICS", "LOGIN"}
)  # fmt: skip
_HEAD_SCAN_LIMIT = 12


@dataclass(frozen=True, slots=True)
class Span:
    start: int
    end: int  # exclusive

    def text(self, src: str) -> str:
        return src[self.start : self.end]


class _Chunk:
    """State of the statement currently being collected."""

    def __init__(self) -> None:
        self.first: int | None = None  # start of first significant token
        self.end = 0  # end of last significant token
        self.paren = 0
        self.prev = ""  # previous significant token, upper-cased for words
        self.n_words = 0
        # block machine (only meaningful when ctx is True)
        self.ctx = False
        self.depth = 0
        self.had_block = False  # a BEGIN-style block really opened
        self.expect_begin = False
        self.slash_only = False
        self.await_catch = False
        self.pending_begin = False
        self.pending_end = False
        self.scan_create = False
        self.type_pending = False
        self.batch_scoped = False  # body runs to GO, unless a BEGIN..END block ends it

    @property
    def nested(self) -> bool:
        """Inside a block: ';' and blank lines must not end the statement."""
        return self.ctx and (
            self.depth > 0
            or self.expect_begin
            or self.slash_only
            or self.await_catch
            or self.pending_begin
        )


_DELIMITER_LINE = re.compile(r"^[ \t]*delimiter[ \t]+(\S+)[ \t]*$", re.I | re.M)


def split(text: str, dialect: str = "generic", blank_line: bool = True) -> list[Span]:
    rules = rules_for(dialect)
    if rules.delimiter_command and _DELIMITER_LINE.search(text):
        return _split_with_delimiter(text, dialect, blank_line, rules)
    spans: list[Span] = []
    ch = _Chunk()

    def close(include_terminator: int | None = None) -> None:
        nonlocal ch
        if ch.first is not None:
            _resolve_pending(ch, None, "", rules)
            end = include_terminator if (include_terminator and ch.had_block) else ch.end
            spans.append(Span(ch.first, end))
        ch = _Chunk()

    skip_to = 0  # tokens before this offset belong to a consumed 'GO 5' line
    for t in tokenize(text, rules):
        if t.start < skip_to:
            continue
        kind = t.kind
        if kind == WS:
            if (
                blank_line
                and ch.first is not None
                and ch.paren == 0
                and not ch.nested
                and text.count("\n", t.start, t.end) >= 2
            ):
                close()
            continue
        if kind in (LINE_COMMENT, BLOCK_COMMENT):
            continue
        if (line_end := _batch_separator_end(text, t, rules)) != -1:
            close()
            skip_to = line_end
            continue
        if kind == SEMI:
            _resolve_pending(ch, SEMI, ";", rules)
            if ch.paren == 0 and not ch.nested:
                close(include_terminator=t.end)
                continue
        word = text[t.start : t.end].upper() if kind == WORD else ""
        if kind == WORD and rules.block is not None:
            _on_word(ch, word, rules.block)
        elif kind != WORD and ch.first is not None:
            _resolve_pending(ch, kind, "", rules)
        if kind == LPAREN:
            ch.paren += 1
        elif kind == RPAREN:
            ch.paren = max(0, ch.paren - 1)
        if ch.first is None:
            ch.first = t.start
        ch.end = t.end
        ch.prev = word or (";" if kind == SEMI else text[t.start : t.end])
        if kind == WORD:
            ch.n_words += 1
    close()
    return spans


def _split_with_delimiter(text: str, dialect: str, blank_line: bool, rules: Rules) -> list[Span]:
    """MySQL client semantics: 'DELIMITER x' lines switch the terminator; they are not SQL."""
    spans: list[Span] = []
    delim, pos = ";", 0
    for m in [*_DELIMITER_LINE.finditer(text), None]:
        end = m.start() if m else len(text)
        segment = text[pos:end]
        if delim == ";":
            spans += [Span(s.start + pos, s.end + pos) for s in split(segment, dialect, blank_line)]
        else:
            spans += [Span(s.start + pos, s.end + pos) for s in _split_on(segment, delim, rules)]
        if m:
            delim, pos = m.group(1), m.end()
    return spans


def _split_on(text: str, delim: str, rules: Rules) -> list[Span]:
    """Split on a custom terminator outside strings and comments; bodies stay whole."""
    spans: list[Span] = []
    first: int | None = None
    last = 0
    skip_to = 0
    for t in tokenize(text, rules):
        if t.start < skip_to or t.kind == WS or t.kind in (LINE_COMMENT, BLOCK_COMMENT):
            continue
        idx = (
            -1 if t.kind in (STRING, QIDENT) else text.find(delim, t.start, t.end + len(delim) - 1)
        )
        if idx != -1 and idx < t.end:  # the terminator can be glued to a word: `end$$`
            if idx > t.start:
                if first is None:
                    first = t.start
                last = idx
            if first is not None:
                spans.append(Span(first, last))
            first, skip_to = None, idx + len(delim)
            continue
        if first is None:
            first = t.start
        last = t.end
    if first is not None:
        spans.append(Span(first, last))
    return spans


def _batch_separator_end(text: str, t: Token, rules: Rules) -> int:
    """If `t` is an Oracle '/' or MSSQL 'GO [n]' alone on its line: that line's end, else -1."""
    word = text[t.start : t.end]
    if t.kind == PUNCT and rules.slash_lines and word == "/":
        tail_ok = lambda rest: not rest  # noqa: E731
    elif t.kind == WORD and rules.go_batches and word.upper() == "GO":
        tail_ok = lambda rest: not rest or rest.isdigit()  # noqa: E731
    else:
        return -1
    ls = text.rfind("\n", 0, t.start) + 1
    le = text.find("\n", t.end)
    le = len(text) if le == -1 else le
    ok = not text[ls : t.start].strip() and tail_ok(text[t.end : le].strip())
    return le if ok else -1


# --- block machine -------------------------------------------------------------------


def _resolve_pending(ch: _Chunk, kind: int | None, word: str, rules: Rules) -> None:
    """Settle a pending BEGIN/END using the token that followed it (None = chunk ends)."""
    if rules.block is None:
        return
    if ch.pending_begin:
        ch.pending_begin = False
        if (kind == WORD and word in rules.block.tx_words) or kind in (SEMI, None):
            if ch.n_words == 1:  # statement-initial BEGIN was a transaction start
                ch.ctx = False
        else:
            _open(ch)
    if ch.pending_end:
        ch.pending_end = False
        _close_block(ch)


def _open(ch: _Chunk) -> None:
    ch.depth += 1
    ch.had_block = True
    ch.expect_begin = False
    ch.await_catch = False


def _close_block(ch: _Chunk) -> None:
    ch.depth = max(0, ch.depth - 1)
    if ch.batch_scoped and ch.depth == 0 and ch.had_block:
        ch.slash_only = False  # a real BEGIN..END body is complete: ';' may end the statement


def _on_word(ch: _Chunk, word: str, br: BlockRules) -> None:
    if ch.pending_begin:
        ch.pending_begin = False
        if word in br.tx_words:
            if ch.n_words == 1:
                ch.ctx = False
        else:
            _open(ch)
    if ch.pending_end:
        ch.pending_end = False
        if word in _END_CLOSERS:
            _close_block(ch)
            if word == "TRY":
                ch.await_catch = True
            ch.prev = word
            return
        _close_block(ch)
    _detect_head(ch, word, br)
    if not ch.ctx:
        return
    if word == "BEGIN":
        ch.pending_begin = True
    elif word == "END":
        ch.pending_end = True
    elif (
        word == "CASE"
        or word in br.inline_openers
        or (word in br.openers and ch.prev in _STMT_START)
    ):
        ch.depth += 1


def _detect_head(ch: _Chunk, word: str, br: BlockRules) -> None:
    """Decide from the first words whether this statement is a procedural block."""
    if ch.n_words == 0:
        if word == "BEGIN" and br.top_begin_block:
            ch.ctx = True
        elif word == "DECLARE" and br.declare_starts_block:
            ch.ctx = ch.expect_begin = True
        elif word == "CREATE":
            ch.scan_create = True
        return
    if not ch.scan_create or ch.n_words > _HEAD_SCAN_LIMIT:
        return
    if ch.type_pending:
        ch.type_pending = ch.scan_create = False
        if word == "BODY" and "TYPE" in br.slash_only_for:
            ch.slash_only = True
        return
    if word in br.routines:
        ch.scan_create = False
        ch.ctx = True
        if word in br.expect_begin_for:
            ch.expect_begin = True
        if word in br.batch_scoped:
            ch.slash_only = ch.batch_scoped = True
        if word == "TYPE":
            ch.type_pending, ch.scan_create = True, True  # TYPE BODY is decided by next word
        elif word in br.slash_only_for:
            ch.slash_only = True
    elif word in _NOT_ROUTINE:
        ch.scan_create = False


# --- cursor lookup -------------------------------------------------------------------


def statement_at(spans: list[Span], text: str, offset: int) -> Span | None:
    """Statement the cursor belongs to.

    Inside a span -> that span. In a gap: right after a statement on the same line
    (e.g. after its ';') -> that statement; in the indentation before a statement on
    the same line -> that statement; otherwise None.
    """
    i = bisect.bisect_right([s.start for s in spans], offset)  # spans[:i] start <= offset
    if i and offset <= spans[i - 1].end:
        return spans[i - 1]
    if i and "\n" not in text[spans[i - 1].end : offset]:
        return spans[i - 1]
    if i < len(spans) and "\n" not in text[offset : spans[i].start]:
        return spans[i]
    return None


def span_lines(text: str, span: Span) -> tuple[int, int]:
    """0-based (first_line, last_line) the span occupies."""
    first = text.count("\n", 0, span.start)
    return first, first + text.count("\n", span.start, span.end)
