import pytest

from sqlide.db.completion import candidates
from sqlide.db.metadata import MetaCache
from sqlide.sql.context import analyze


@pytest.fixture
async def meta(session):
    await session.execute("create schema app")
    await session.execute("create table app.users (id int primary key, name varchar(9))")
    await session.execute("create table orders (oid int, user_id int)")
    return MetaCache(session)


async def complete(meta, sql: str):
    offset = sql.index("|")
    ctx = analyze(sql.replace("|", ""), offset, "generic")
    return await candidates(ctx, meta, "generic")


def texts(cs, kind=None):
    return [c.text for c in cs if kind is None or c.kind == kind]


async def test_tables_after_from_include_current_schema_and_schemas(meta):
    cs = await complete(meta, "select * from |")
    assert "ORDERS" in texts(cs, "table")
    assert "APP" in texts(cs, "schema")


async def test_prefix_filters_case_insensitively(meta):
    cs = await complete(meta, "select * from ord|")
    assert texts(cs, "table") == ["ORDERS"]


async def test_alias_dot_gives_columns(meta):
    cs = await complete(meta, "select u.| from app.users u")
    assert texts(cs) == ["ID", "NAME"]
    assert cs[0].detail == "INTEGER · pk"


async def test_schema_dot_gives_tables(meta):
    cs = await complete(meta, "select * from app.|")
    assert texts(cs) == ["USERS"]


async def test_select_list_columns_from_statement_tables(meta):
    cs = await complete(meta, "select | from app.users u join orders o on 1=1")
    cols = texts(cs, "column")
    assert {"ID", "NAME", "OID", "USER_ID"} <= set(cols)
    assert texts(await complete(meta, "select count| from app.users"), "function") == ["count"]


async def test_keywords_follow_typed_case(meta):
    assert "select" in texts(await complete(meta, "sel|"), "keyword")
    assert "SELECT" in texts(await complete(meta, "SEL|"), "keyword")


async def test_unknown_table_degrades_gracefully(meta):
    cs = await complete(meta, "select | from nothing")
    assert texts(cs, "column") == []
    assert texts(cs, "keyword")


async def test_works_without_metadata():
    ctx = analyze("sel", 3, "generic")
    assert "select" in texts(await candidates(ctx, None, "generic"))
