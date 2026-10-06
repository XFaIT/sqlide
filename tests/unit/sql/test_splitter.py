import pytest

from sqlide.sql.splitter import span_lines, split, statement_at


def stmts(text, dialect="generic", blank_line=True):
    return [s.text(text) for s in split(text, dialect, blank_line)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("select 1; select 2;", ["select 1", "select 2"]),
        ("select 1;;; select 2", ["select 1", "select 2"]),
        ("select 'a;b'; select 2", ["select 'a;b'", "select 2"]),
        ('select "a;b" from t; x', ['select "a;b" from t', "x"]),
        ("select 1 -- ;\n; select 2", ["select 1", "select 2"]),
        ("select /* ; */ 1; select 2", ["select /* ; */ 1", "select 2"]),
        ("-- c\nselect 1;", ["select 1"]),
        ("-- only a comment\n", []),
        ("select 1; -- trailing\nselect 2", ["select 1", "select 2"]),
        ("", []),
        ("   \n\n  ", []),
        ("select 'unterminated; select 2", ["select 'unterminated; select 2"]),
    ],
)
def test_generic(text, expected):
    assert stmts(text) == expected


def test_blank_line_splits_and_can_be_disabled():
    t = "select 1\n\nselect 2\nfrom t"
    assert stmts(t) == ["select 1", "select 2\nfrom t"]
    assert stmts(t, blank_line=False) == ["select 1\n\nselect 2\nfrom t"]


def test_blank_line_inside_parens_does_not_split():
    assert stmts("select (1\n\n+ 2)") == ["select (1\n\n+ 2)"]


def test_comment_line_between_does_not_split_without_blank_line():
    assert stmts("select 1\n-- c\nfrom t") == ["select 1\n-- c\nfrom t"]


def test_comment_only_chunk_after_blank_is_dropped():
    assert stmts("-- note\n\nselect 1") == ["select 1"]


def test_postgres_dollar_quotes():
    f = "create function f() returns int as $$ begin select 1; select 2; end $$ language sql"
    assert stmts(f + "; select 3", "postgres") == [f, "select 3"]
    tagged = "do $body$ begin perform 1; end $body$"
    assert stmts(tagged + ";", "postgres") == [tagged]
    assert stmts("select $1; select $2", "postgres") == ["select $1", "select $2"]


def test_postgres_nested_comment_and_tx():
    assert stmts("/* a /* ; */ ; */ select 1", "postgres") == ["select 1"]
    assert stmts("begin; select 1; commit;", "postgres") == ["begin", "select 1", "commit"]


def test_e_string_backslash():
    assert stmts("select E'it\\'s;'; select 2", "postgres") == ["select E'it\\'s;'", "select 2"]


def test_mysql_lexing():
    assert stmts("select 'a\\'b;c'; select 2", "mysql") == ["select 'a\\'b;c'", "select 2"]
    assert stmts("select `a;b`; # c;\nselect 2", "mysql") == ["select `a;b`", "select 2"]


def test_mysql_blocks():
    proc = (
        "create procedure p() begin declare x int; if x > 0 then set x = 1; end if;"
        " while x < 3 do set x = x + 1; end while; case when x = 1 then set x = 2; end case; end;"
    )
    assert stmts(proc + " select 2", "mysql") == [proc, "select 2"]
    assert stmts("select if(1,2,3); select 2", "mysql") == ["select if(1,2,3)", "select 2"]
    assert stmts("begin; select 1", "mysql") == ["begin", "select 1"]
    assert stmts(
        "create trigger t before insert on a for each row set new.x = 1; select 2", "mysql"
    ) == [
        "create trigger t before insert on a for each row set new.x = 1",
        "select 2",
    ]
    assert stmts("create table if not exists t (a int); select 2", "mysql") == [
        "create table if not exists t (a int)",
        "select 2",
    ]


def test_oracle_q_quote_and_plain_end_column():
    assert stmts("select q'[it's ; ok]' from dual; select 2 from dual", "oracle") == [
        "select q'[it's ; ok]' from dual",
        "select 2 from dual",
    ]
    assert stmts("select end, loop from t; select 2", "oracle") == [
        "select end, loop from t",
        "select 2",
    ]


def test_oracle_blocks_keep_terminator():
    anon = "begin null; end;"
    assert stmts(anon + "\nselect 1 from dual", "oracle") == [anon, "select 1 from dual"]
    decl = "declare x number; begin x := 1; end;"
    assert stmts(decl, "oracle") == [decl]
    proc = (
        "create or replace procedure p is v number; begin v := 1; if v > 0 then v := 2; end if;"
        " for i in 1..3 loop null; end loop;"
        " select case when 1 = 1 then 1 end into v from dual; end;"
    )
    assert stmts(proc + "\n\nselect 2 from dual", "oracle") == [proc, "select 2 from dual"]


def test_oracle_blank_line_inside_block():
    blk = "begin\n  null;\n\n  null;\nend;"
    assert stmts(blk, "oracle") == [blk]


def test_oracle_slash_terminator_and_package():
    assert stmts("begin\n null;\nend;\n/\nselect 1 from dual", "oracle") == [
        "begin\n null;\nend;",
        "select 1 from dual",
    ]
    pkg = "create package body pk is procedure a is begin null; end; end pk;"
    assert stmts(pkg + "\n/\nselect 1 from dual", "oracle") == [pkg, "select 1 from dual"]
    assert stmts("create type t as object (a int);", "oracle") == [
        "create type t as object (a int)"
    ]
    tb = "create type body t is member function f return number is begin return 1; end; end;"
    assert stmts(tb + "\n/", "oracle") == [tb]


def test_mssql_go_and_tx():
    assert stmts("select 1\ngo\nselect 2", "mssql") == ["select 1", "select 2"]
    assert stmts("select 1\nGO 3\nselect 2", "mssql") == ["select 1", "select 2"]
    assert stmts("begin tran; select 1; commit", "mssql") == ["begin tran", "select 1", "commit"]
    assert stmts("select [a;b]; select 2", "mssql") == ["select [a;b]", "select 2"]


def test_mssql_try_catch_and_nested_tran():
    tc = "begin try select 1/0; end try\n\nbegin catch select 2; end catch;"
    assert stmts(tc + " select 3", "mssql") == [tc, "select 3"]
    proc = "create procedure p as begin begin transaction; select 1; commit; end;"
    assert stmts(proc + " select 2", "mssql") == [proc, "select 2"]


def test_sqlite_trigger_and_tx():
    trg = "create trigger t after insert on a begin update b set x = 1; update c set y = 2; end;"
    assert stmts(trg + " select 1", "sqlite") == [trg, "select 1"]
    assert stmts("begin transaction; select 1", "sqlite") == ["begin transaction", "select 1"]


def test_go_is_not_special_outside_mssql():
    assert stmts("select 1\ngo\nselect 2", "generic") == ["select 1\ngo\nselect 2"]


SRC = "select 1;\n\nselect 2\nfrom t;\n"


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (0, "select 1"),
        (5, "select 1"),
        (8, "select 1"),  # right before ';'
        (9, "select 1"),  # right after ';'
        (10, None),  # empty line after a statement
        (11, "select 2\nfrom t"),
        (20, "select 2\nfrom t"),
        (len("select 1;\n\nselect 2\nfrom t;"), "select 2\nfrom t"),  # right after final ';'
        (len(SRC), None),
    ],
)
def test_statement_at(offset, expected):
    spans = split(SRC)
    got = statement_at(spans, SRC, offset)
    assert (got.text(SRC) if got else None) == expected


def test_statement_at_indentation_before_statement():
    t = "select 1;\n   select 2"
    spans = split(t)
    assert statement_at(spans, t, 12).text(t) == "select 2"  # inside the indent


def test_statement_at_no_statements():
    assert statement_at([], "  ", 1) is None


def test_span_lines():
    spans = split(SRC)
    assert [span_lines(SRC, s) for s in spans] == [(0, 0), (2, 3)]


def test_fuzz_invariants_all_dialects():
    import random

    from sqlide.sql.dialects import RULES

    frags = ["select", "begin", "end", "if", "loop", "case", ";", "(", ")", "'", '"', "$$", "/*",
             "*/", "--", "\n", "\n\n", " ", "/", "go", "q'[", "]'", "`", "[", "]", "create",
             "procedure", "declare", "try", "catch", "x", "1"]  # fmt: skip
    rng = random.Random(1234)
    for dialect in RULES:
        for _ in range(400):
            text = "".join(rng.choice(frags) for _ in range(rng.randint(0, 40)))
            spans = split(text, dialect)
            prev_end = 0
            for sp in spans:
                assert prev_end <= sp.start < sp.end <= len(text), (dialect, text)
                assert not text[sp.start].isspace()  # (an unterminated quote may end in spaces)
                prev_end = sp.end
