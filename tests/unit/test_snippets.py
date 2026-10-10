import pytest

from sqlide.sql.snippets import is_ddl, qualified_name, quote_ident, select_all


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
        # Databricks / Spark: backticks, never double quotes (they are string literals there)
        ("dbt-analytics", "databricks", "`dbt-analytics`"),
        ("orders", "databricks", "orders"),
        ("Orders", "databricks", "Orders"),
        ("order", "databricks", "`order`"),
        ("a`b", "databricks", "`a``b`"),
        ("order", "postgres", '"order"'),
        ("user", "mssql", "[user]"),
        ("dbt-analytics", "clickhouse", "`dbt-analytics`"),
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


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("create table t(a int)", True),
        ("  DROP VIEW v", True),
        ("-- note\n/* x */ alter table t add b int", True),
        ("select 1", False),
        ("insert into t values (1)", False),
        ("created_at", False),
        ("", False),
    ],
)
def test_is_ddl(sql, expected):
    assert is_ddl(sql) is expected


def test_databricks_select_all_uses_backticks_and_limit():
    name = qualified_name(["main", "dbt-analytics", "orders"], "databricks")
    assert select_all(name, "databricks") == "SELECT * FROM main.`dbt-analytics`.orders LIMIT 100"


def test_dialect_for_recognises_spark_urls_only_for_generic_drivers():
    from sqlide.sql.dialects import dialect_for

    assert dialect_for("jdbc:databricks://h:443/default;httpPath=x", "generic") == "databricks"
    assert dialect_for("jdbc:spark://h:443", "generic") == "databricks"
    assert dialect_for("jdbc:postgresql://h/db", "generic") == "generic"
    assert dialect_for("jdbc:databricks://h", "postgres") == "postgres"
