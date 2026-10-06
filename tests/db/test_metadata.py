from sqlide.db.metadata import MetaCache


async def test_schema_table_column_roundtrip(session):
    await session.execute("create schema app")
    await session.execute("create table app.users (id int primary key, name varchar(20) not null)")
    await session.execute("create view app.v as select 1 as x")
    meta = MetaCache(session)
    ns = next(n for n in await meta.namespaces() if n.name == "APP")
    tables = await meta.tables(ns)
    assert [(t.name, t.is_view) for t in tables] == [("USERS", False), ("V", True)]
    cols = await meta.columns(tables[0])
    assert [(c.name, c.primary_key, c.nullable) for c in cols] == [
        ("ID", True, False),
        ("NAME", False, False),
    ]
    assert tables[0].qualified == "APP.USERS"


async def test_cache_until_refresh(session):
    meta = MetaCache(session)
    ns = next(n for n in await meta.namespaces() if n.name == "PUBLIC")
    assert await meta.tables(ns) == []
    await session.execute("create table t1 (a int)")
    assert await meta.tables(ns) == []  # cached
    meta.refresh()
    ns = next(n for n in await meta.namespaces() if n.name == "PUBLIC")
    assert [t.name for t in await meta.tables(ns)] == ["T1"]
