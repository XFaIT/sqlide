"""SQLite and DuckDB: real drivers from Maven Central, no server needed."""

import pytest
from tests.conftest import CACHE

from sqlide.db.completion import candidates
from sqlide.db.metadata import MetaCache
from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry
from sqlide.sql.context import analyze
from sqlide.sql.splitter import split


@pytest.fixture(params=["sqlite", "duckdb"])
async def emb(request, tmp_path):
    kind = request.param
    reg = DriverRegistry(CACHE / "drivers", CACHE / "drivers.toml")
    if not reg.is_installed(kind):
        reg.install(kind)
    defn = reg.get(kind)
    url = f"jdbc:{kind}:{tmp_path / 'db'}"
    s = DbSession(load_driver(defn, reg.jar_paths(kind)), url, dialect=defn.dialect)
    await s.open()
    s.kind = kind  # type: ignore[attr-defined]
    yield s
    await s.close()


async def run(s, script):
    return [await s.execute(sp.text(script)) for sp in split(script, "sqlite")]


async def test_script_types_and_counts(emb):
    script = """
create table t (id integer primary key, name text, born date, note text);
insert into t values (1, 'тест', '2024-02-29', null), (2, 'b', null, 'x;y');
-- comment ; with semicolon
update t set note = 'z' where id = 2;
select id, name, born, note from t order by id;
"""
    res = await run(emb, script)
    assert res[2].items[0].update_count == 1
    rows = res[-1].items[0].rows
    assert rows[0][1] == "тест" and rows[0][3] is None
    assert rows[1][3] == "z"
    assert "2024-02-29" in str(rows[0][2])


async def test_paging(emb):
    await emb.execute("create table n (v integer)")
    await emb.execute("insert into n select * from (" + _series(emb.kind, 1200) + ")")
    ex = await emb.execute("select v from n", page_size=500)
    item = ex.items[0]
    total = len(item.rows)
    while item.cursor is not None:
        rows, done = await item.cursor.fetch_more(500)
        total += len(rows)
        if done:
            break
    assert total == 1200


def _series(kind: str, n: int) -> str:
    if kind == "duckdb":
        return f"select * from range({n})"
    return (
        f"with recursive s(v) as (select 1 union all select v+1 from s where v < {n}) "
        "select v from s"
    )


async def test_error_and_recovery(emb):
    from sqlide.db.result import DbError

    with pytest.raises(DbError):
        await emb.execute("select * from missing_table")
    assert (await emb.execute("select 1")).items[0].rows[0][0] == 1


async def test_manual_transaction(emb):
    await emb.execute("create table m (a integer)")
    await emb.set_autocommit(False)
    await emb.execute("insert into m values (1)")
    await emb.rollback()
    assert (await emb.execute("select count(*) from m")).items[0].rows[0][0] == 0
    await emb.execute("insert into m values (2)")
    await emb.commit()
    assert (await emb.execute("select count(*) from m")).items[0].rows[0][0] == 1


async def test_metadata_and_completion(emb):
    await emb.execute("create table people (id integer, full_name text)")
    meta = MetaCache(emb)
    spaces = await meta.namespaces()
    tables = []
    for ns in spaces:
        tables += [t for t in await meta.tables(ns) if t.name == "people"]
    assert tables, f"people not found in {[n.name for n in spaces]}"
    cols = await meta.columns(tables[0])
    assert [c.name for c in cols] == ["id", "full_name"]
    sql = "select ful| from people"
    ctx = analyze(sql.replace("|", ""), sql.index("|"), "sqlite")
    assert "full_name" in [c.text for c in await candidates(ctx, meta, "sqlite")]
