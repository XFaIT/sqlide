"""Tolerant SQL tokenizer. Never raises: unterminated strings/comments run to EOF."""

from __future__ import annotations

import re
from typing import NamedTuple

from sqlide.sql.dialects import Rules

WS, LINE_COMMENT, BLOCK_COMMENT, STRING, QIDENT, WORD, PUNCT, SEMI, LPAREN, RPAREN = range(10)

_WS = re.compile(r"\s+")
_WORD = re.compile(r"[\w$#@]+")
_DOLLAR = re.compile(r"\$(?:[^\W\d]\w*)?\$")
_Q_CLOSE = {"[": "]", "{": "}", "<": ">", "(": ")"}


class Token(NamedTuple):
    kind: int
    start: int
    end: int


def _scan_quoted(text: str, i: int, quote: str, backslash: bool) -> int:
    """`i` is on the opening quote; doubled quote escapes it. Returns end (exclusive)."""
    n, j = len(text), i + 1
    if backslash:
        while j < n:
            ch = text[j]
            if ch == "\\":
                j += 2
            elif ch == quote:
                if text[j + 1 : j + 2] == quote:
                    j += 2
                else:
                    return j + 1
            else:
                j += 1
        return n
    while True:
        k = text.find(quote, j)
        if k == -1:
            return n
        if text[k + 1 : k + 2] == quote:
            j = k + 2
            continue
        return k + 1


def tokenize(text: str, rules: Rules) -> list[Token]:
    out: list[Token] = []
    n, i = len(text), 0
    add = out.append
    while i < n:
        c = text[i]
        two = text[i : i + 2]
        if c.isspace():
            j = _WS.match(text, i).end()  # type: ignore[union-attr]
            add(Token(WS, i, j))
        elif two == "--" or (c == "#" and rules.hash_comment):
            j = text.find("\n", i)
            j = n if j == -1 else j
            add(Token(LINE_COMMENT, i, j))
        elif two == "/*":
            j = _scan_block_comment(text, i, rules.nested_comments)
            add(Token(BLOCK_COMMENT, i, j))
        elif c == "'":
            j = _scan_quoted(text, i, "'", rules.backslash_escapes)
            add(Token(STRING, i, j))
        elif c in "eE" and rules.e_strings and text[i + 1 : i + 2] == "'":
            j = _scan_quoted(text, i + 1, "'", True)
            add(Token(STRING, i, j))
        elif c in "qQ" and rules.q_quote and text[i + 1 : i + 2] == "'" and _q_ok(text, i + 2):
            j = _scan_q(text, i)
            add(Token(STRING, i, j))
        elif c == '"':
            j = _scan_quoted(text, i, '"', rules.backslash_escapes)
            add(Token(QIDENT, i, j))
        elif c == "`" and rules.backtick:
            add(Token(QIDENT, i, _scan_quoted(text, i, "`", False)))
        elif c == "[" and rules.brackets:
            add(Token(QIDENT, i, _scan_bracket(text, i)))
        elif c == "$" and rules.dollar_quotes and (m := _DOLLAR.match(text, i)):
            tag = m.group(0)
            k = text.find(tag, m.end())
            add(Token(STRING, i, n if k == -1 else k + len(tag)))
            i = out[-1].end
            continue
        elif c == ";":
            add(Token(SEMI, i, i + 1))
            i += 1
            continue
        elif c == "(":
            add(Token(LPAREN, i, i + 1))
            i += 1
            continue
        elif c == ")":
            add(Token(RPAREN, i, i + 1))
            i += 1
            continue
        elif m := _WORD.match(text, i):
            add(Token(WORD, i, m.end()))
        else:
            add(Token(PUNCT, i, i + 1))
            i += 1
            continue
        i = out[-1].end
    return out


def _scan_block_comment(text: str, i: int, nested: bool) -> int:
    n, depth, j = len(text), 1, i + 2
    while j < n:
        if text.startswith("*/", j):
            depth -= 1
            j += 2
            if depth == 0:
                return j
        elif nested and text.startswith("/*", j):
            depth += 1
            j += 2
        else:
            j += 1
    return n


def _scan_bracket(text: str, i: int) -> int:
    n, j = len(text), i + 1
    while j < n:
        if text[j] == "]":
            if text[j + 1 : j + 2] == "]":
                j += 2
                continue
            return j + 1
        j += 1
    return n


def _q_ok(text: str, i: int) -> bool:
    return i < len(text) and not text[i].isspace()


def _scan_q(text: str, i: int) -> int:
    """q'[ ... ]' style quoting; `i` is on the q."""
    d = text[i + 2]
    closing = _Q_CLOSE.get(d, d) + "'"
    k = text.find(closing, i + 3)
    return len(text) if k == -1 else k + 2
