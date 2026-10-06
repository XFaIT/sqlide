import pytest

from sqlide.sql.format import FormatError, format_sql, toggle_line_comments


def test_formats_single_statement():
    assert format_sql("select a,b from t where x=1", "postgres") == (
        "SELECT\n  a,\n  b\nFROM t\nWHERE\n  x = 1"
    )


def test_formats_several_statements_separated_by_blank_line():
    out = format_sql("select 1; select 2", "generic")
    assert out == "SELECT\n  1;\n\nSELECT\n  2"


def test_mssql_maps_to_tsql():
    assert format_sql("select top 5 a from t", "mssql").split()[:3] == ["SELECT", "TOP", "5"]


def test_unparsable_raises_format_error():
    with pytest.raises(FormatError):
        format_sql("select from where", "generic")


def test_comment_and_uncomment_roundtrip():
    lines = ["select 1", "  from t", "", "where x"]
    commented = toggle_line_comments(lines)
    assert commented == ["-- select 1", "--   from t", "", "-- where x"]
    assert toggle_line_comments(commented) == lines


def test_mixed_lines_get_commented_and_blank_only_untouched():
    assert toggle_line_comments(["-- a", "b"]) == ["-- -- a", "-- b"]
    assert toggle_line_comments(["", "  "]) == ["", "  "]


def test_indentation_is_preserved_at_the_minimum():
    assert toggle_line_comments(["    a", "  b"]) == ["  --   a", "  -- b"]
