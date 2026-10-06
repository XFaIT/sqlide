from sqlide.sql import lexer as L
from sqlide.sql.dialects import rules_for


def kinds(text, dialect="generic"):
    return [(t.kind, text[t.start : t.end]) for t in L.tokenize(text, rules_for(dialect))]


def test_basic_tokens():
    assert kinds("a (b);") == [
        (L.WORD, "a"), (L.WS, " "), (L.LPAREN, "("), (L.WORD, "b"), (L.RPAREN, ")"), (L.SEMI, ";"),
    ]  # fmt: skip


def test_string_escaped_quote_and_unterminated():
    assert kinds("'it''s'") == [(L.STRING, "'it''s'")]
    assert kinds("'abc") == [(L.STRING, "'abc")]  # tolerant: runs to EOF


def test_comments():
    assert kinds("-- x\n1")[0] == (L.LINE_COMMENT, "-- x")
    assert kinds("/* a */")[0][0] == L.BLOCK_COMMENT
    assert kinds("/* open")[0] == (L.BLOCK_COMMENT, "/* open")


def test_nested_comment_only_postgres():
    assert kinds("/* a /* b */ c */x", "postgres")[0][1] == "/* a /* b */ c */"
    assert kinds("/* a /* b */ c */x", "oracle")[0][1] == "/* a /* b */"


def test_dollar_quote_and_positional_param():
    assert kinds("$$a;b$$", "postgres") == [(L.STRING, "$$a;b$$")]
    assert kinds("$f$ x $f$", "postgres")[0][0] == L.STRING
    assert kinds("$1", "postgres") == [(L.WORD, "$1")]
    assert kinds("$$a$$", "mysql")[0][0] != L.STRING  # not a dollar-quoting dialect


def test_backslash_escapes_mysql_vs_standard():
    assert kinds(r"'a\'b'", "mysql") == [(L.STRING, r"'a\'b'")]
    assert kinds(r"'a\'b'", "postgres")[0] == (L.STRING, r"'a\'")  # standard strings
    assert kinds(r"E'a\'b'", "postgres") == [(L.STRING, r"E'a\'b'")]


def test_quoted_identifiers():
    assert kinds('"a;b"')[0] == (L.QIDENT, '"a;b"')
    assert kinds("`a;b`", "mysql")[0] == (L.QIDENT, "`a;b`")
    assert kinds("[a;b]", "mssql")[0] == (L.QIDENT, "[a;b]")
    assert kinds("[a]]b]", "mssql")[0] == (L.QIDENT, "[a]]b]")


def test_oracle_q_quote():
    assert kinds("q'[it's;]'", "oracle") == [(L.STRING, "q'[it's;]'")]
    assert kinds("q'!x'y!'", "oracle") == [(L.STRING, "q'!x'y!'")]


def test_mysql_hash_comment():
    assert kinds("# hi;\n1", "mysql")[0] == (L.LINE_COMMENT, "# hi;")
