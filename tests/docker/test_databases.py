"""Same scenario against MySQL, MariaDB and ClickHouse."""

import contextlib

import pytest

from sqlide.db.completion import candidates
from sqlide.db.metadata import MetaCache
from sqlide.db.result import DbError
from sqlide.sql.context import analyze
from sqlide.sql.splitter import split

pytestmark = pytest.mark.docker


ENGINE = {"clickhouse": " engine=MergeTree order by id"}
DIALECT = {"clickhouse": "clickhouse", "mssql": "mssql", "oracle": "oracle"}
SLEEP = {
    "mssql": "waitfor delay '00:00:30'",
    "oracle": "select count(*) from (select 1 from dual connect by level <= 1000000000)",
    "clickhouse": "select sleep(3), count() from numbers(1)",
}


def n_rows(kind: str, n: int) -> str:
    if kind == "clickhouse":
        return f"select number as g from numbers({n})"
    if kind == "mssql":
        return f"select top {n} 1 as g from sys.all_columns a cross join sys.all_columns b"
    if kind == "oracle":
        return f"select 1 as g from dual connect by level <= {n}"
    return (
        "select 1 as g from information_schema.columns a "
        f"cross join information_schema.columns b limit {n}"
    )


async def test_connects_and_reports_product(db):
    assert db.product and db.connected


async def test_simple_select_and_types(db):
    ex = await db.execute("select 1 as a, 'x' as b, cast(1.50 as decimal(10,2)) as c, null as d")
    row = ex.items[0].rows[0]
    assert int(row[0]) == 1 and row[1] == "x" and float(row[2]) == 1.5 and row[3] is None


async def test_paging_fetches_everything(db):
    ex = await db.execute(n_rows(db.kind, 1200), page_size=500)
    item = ex.items[0]
    total = len(item.rows)
    while item.cursor is not None:
        rows, done = await item.cursor.fetch_more(500)
        total += len(rows)
        if done:
            break
    assert total == 1200


async def test_error_has_message_and_session_survives(db):
    with pytest.raises(DbError):
        await db.execute("select * from definitely_missing_table")
    assert (await db.execute("select 1")).items[0].rows == [(1,)]


async def test_ddl_dml_roundtrip(db):
    engine = ENGINE.get(db.kind, "")
    await db.execute("drop table if exists sqlide_t")
    await db.execute(f"create table sqlide_t (id int, name varchar(20)){engine}")
    await db.execute("insert into sqlide_t values (1, 'a'), (2, 'b')")
    ex = await db.execute("select id, name from sqlide_t order by id")
    assert ex.items[0].rows == [(1, "a"), (2, "b")]


async def test_metadata_tree_and_completion(db):
    engine = ENGINE.get(db.kind, "")
    await db.execute("drop table if exists sqlide_m")
    await db.execute(f"create table sqlide_m (id int, title varchar(20)){engine}")
    meta = MetaCache(db)
    spaces = await meta.namespaces()
    assert spaces, "no schemas/catalogs listed"
    current = await meta.current_namespace()
    ns = next((n for n in spaces if n.name.lower() == current.lower()), None)
    assert ns is not None, f"current namespace {current!r} not in {[n.name for n in spaces]}"
    tables = await meta.tables(ns)
    table = next(t for t in tables if t.name.lower() == "sqlide_m")
    cols = await meta.columns(table)
    assert [c.name.lower() for c in cols] == ["id", "title"]
    sql = "select ti| from sqlide_m"
    ctx = analyze(sql.replace("|", ""), sql.index("|"), db_dialect(db))
    found = [c.text for c in await candidates(ctx, meta, db_dialect(db))]
    assert "title" in [f.lower() for f in found]


def db_dialect(db) -> str:
    return DIALECT.get(db.kind, "mysql")


async def test_splitter_statements_run_as_split(db):
    sql = "select 1 as a; -- c\nselect 2 as a;\n\nselect 3 as a"
    got = []
    for span in split(sql, db_dialect(db)):
        got.append((await db.execute(span.text(sql))).items[0].rows[0][0])
    assert got == [1, 2, 3]


async def test_cancel_long_query(db):
    import asyncio

    sleeper = (
        "select sleep(30)"
        if db.kind != "clickhouse"
        else "select sleep(3), count() from numbers(1)"
    )
    task = asyncio.create_task(db.execute(sleeper))
    await asyncio.sleep(1)
    db.cancel()
    with contextlib.suppress(DbError):
        await asyncio.wait_for(task, 15)
    assert (await db.execute("select 1")).items[0].rows == [(1,)]


async def run_script(db, script: str):
    results = []
    for span in split(script, db_dialect(db)):
        ex = await db.execute(span.text(script))
        results.append(ex)
    return results


async def test_mysql_delimiter_script_creates_and_calls_procedure(db):
    if db.kind not in ("mysql", "mariadb"):
        pytest.skip("MySQL-family only")
    script = """\
DROP PROCEDURE IF EXISTS sqlide_p;
DELIMITER $$
CREATE PROCEDURE sqlide_p()
BEGIN
  SELECT 1 AS a;

  SELECT 2 AS b;
END$$
DELIMITER ;
CALL sqlide_p();
"""
    results = await run_script(db, script)
    call = results[-1]
    assert [item.rows[0][0] for item in call.items if item.has_rows] == [1, 2]


async def test_mssql_procedure_without_begin_runs_to_go(db):
    if db.kind != "mssql":
        pytest.skip("SQL Server only")
    script = """\
drop procedure if exists sqlide_p
go
create procedure sqlide_p as
select 11 as x;

select 22 as y;
go
exec sqlide_p
"""
    results = await run_script(db, script)
    rows = [i.rows[0][0] for i in results[-1].items if i.has_rows]
    assert rows == [11, 22]
