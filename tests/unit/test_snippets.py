import pytest

from sqlide.sql.snippets import qualified_name, quote_ident, select_all


@pytest.mark.parametrize(
    ("name", "dialect", "expected"),
    [
        ("users", "postgres", "users"),
        ("Users", "postgres", '"Users"'),
        ("USERS", "postgres", '"USERS"'),
        ("USERS", "generic", "USERS"),
        ("users", "generic", '"users"'),
        ("my table", "mysql", "`my table`"),
        ("Users", "mysql", "Users"),
        ("a b", "mssql", "[a b]"),
        ('we"ird', "postgres", '"we""ird"'),
        ("1abc", "postgres", '"1abc"'),
    ],
)
def test_quote_ident(name, dialect, expected):
    assert quote_ident(name, dialect) == expected


def test_qualified_skips_empty_parts():
    assert qualified_name(["", "public", "t"], "postgres") == "public.t"


@pytest.mark.parametrize(
    ("dialect", "sql"),
    [
        ("postgres", "SELECT * FROM t LIMIT 5"),
        ("mssql", "SELECT TOP 5 * FROM t"),
        ("oracle", "SELECT * FROM t FETCH FIRST 5 ROWS ONLY"),
    ],
)
def test_select_all(dialect, sql):
    assert select_all("t", dialect, 5) == sql
