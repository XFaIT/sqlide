import datetime as dt
import json
from decimal import Decimal

from sqlide.grid import copyfmt as c
from sqlide.grid.formatting import format_value, raw_text

HEAD = ["id", "Name", "note"]
ROWS = [(1, "a|b", None), (2, 'say "hi"\nnow', Decimal("1.50"))]


def test_tsv_plain_and_with_header():
    assert c.to_tsv([(1, "x", None)]) == "1\tx\t"
    assert c.to_tsv([(1, "x", None)], HEAD) == "id\tName\tnote\n1\tx\t"


def test_tsv_quotes_cells_with_tabs_newlines_quotes():
    assert c.to_tsv([("a\tb", 'q"', "l1\nl2")]) == '"a\tb"\t"q"""\t"l1\nl2"'


def test_csv():
    out = c.to_csv(ROWS, HEAD)
    assert out.splitlines()[0] == "id,Name,note"
    assert '"say ""hi""\nnow"' in out and out.endswith("1.50")


def test_markdown_escapes_pipes_and_newlines():
    out = c.to_markdown(ROWS, HEAD)
    assert out.splitlines()[1] == "| --- | --- | --- |"
    assert "a\\|b" in out and 'say "hi"<br>now' in out


def test_json_types():
    rows = [(1, dt.datetime(2026, 1, 2, 3, 4, 5), Decimal("2.5"), Decimal("3"), b"\x01", None)]
    head = ["a", "b", "c", "d", "e", "f"]
    got = json.loads(c.to_json(rows, head))[0]
    assert got == {"a": 1, "b": "2026-01-02 03:04:05", "c": 2.5, "d": 3, "e": "0x01", "f": None}


def test_insert_sql_literals_and_identifier_quoting():
    rows = [(1, "o'brien", None, True, b"\xca\xfe", 1.5, dt.date(2026, 1, 2))]
    head = ["id", "Mixed Name", "n", "ok", "bin", "f", "d"]
    sql = c.to_insert_sql(rows, head, "public.t")
    assert sql == (
        'INSERT INTO public.t (id, "Mixed Name", n, ok, bin, f, d) '
        "VALUES (1, 'o''brien', NULL, TRUE, X'cafe', 1.5, '2026-01-02');"
    )


def test_raw_text_vs_display_text():
    assert raw_text(None) == "" and format_value(None) == "<null>"
    assert raw_text(b"\xde\xad") == "0xdead"
    long = bytes(range(40))
    assert "40 bytes" in format_value(long) and raw_text(long) == "0x" + long.hex()
    assert raw_text(Decimal("1E+2")) == "100"
    assert format_value("a\nb\tc") == "a⏎b⇥c" and raw_text("a\nb\tc") == "a\nb\tc"
    assert raw_text(dt.datetime(2026, 1, 2, 3, 4, 5)) == "2026-01-02 03:04:05"
