"""Wider SQL behaviour on real servers: types, scripts, results, transactions."""

import datetime as dt
import decimal

import pytest

from sqlide.db.result import DbError
from sqlide.sql.splitter import split

pytestmark = pytest.mark.docker


async def run(session, script: str, dialect: str):
    out = []
    for span in split(script, dialect):
        out.append(await session.execute(span.text(script)))
    return out


# ---------- PostgreSQL ----------


async def test_pg_script_with_dollar_quotes_and_returning(pg):
    script = """
drop table if exists bat;
create table bat (id serial primary key, name text, meta jsonb);
do $$
begin
  insert into bat(name) values ('a;b');
  insert into bat(name) values ('c');
end
$$;
insert into bat(name, meta) values ('x', '{"k": [1,2]}') returning id, name;
select count(*) from bat;
"""
    res = await run(pg, script, "postgres")
    returning = res[-2].items[0]
    assert returning.rows[0][1] == "x"
    assert res[-1].items[0].rows[0][0] == 3


async def test_pg_update_counts_and_multi_statement_in_one_execute(pg):
    await pg.execute("drop table if exists bat2")
    await pg.execute("create table bat2 as select g from generate_series(1, 10) g")
    ex = await pg.execute("update bat2 set g = g + 1 where g > 5")
    assert ex.items[0].update_count == 5
    ex = await pg.execute("select 1 as a; select 2 as b")  # one JDBC call, two result sets
    assert [i.rows[0][0] for i in ex.items if i.has_rows] == [1, 2]


async def test_pg_more_types(pg):
    ex = await pg.execute(
        "select 9223372036854775807::bigint, 1e400::numeric, 'тест 😀'::text, true, "
        "interval '1 day 2 hours', '10.0.0.1'::inet, '2024-02-29'::date, "
        "'2024-02-29 12:00:00+02'::timestamptz, '12:34:56'::time, repeat('x', 100000)"
    )
    r = ex.items[0].rows[0]
    assert r[0] == 9223372036854775807
    assert isinstance(r[1], decimal.Decimal)
    assert r[2] == "тест 😀" and r[3] is True
    assert "1 day" in str(r[4]) and str(r[5]) == "10.0.0.1"
    assert r[6] == dt.date(2024, 2, 29)
    assert isinstance(r[7], dt.datetime) and isinstance(r[8], dt.time)
    assert len(r[9]) == 100000


async def test_pg_manual_transaction_commit_and_rollback(pg):
    await pg.execute("drop table if exists bat3")
    await pg.execute("create table bat3(a int)")
    await pg.set_autocommit(False)
    await pg.execute("insert into bat3 values (1)")
    assert pg.pending_tx
    await pg.rollback()
    assert (await pg.execute("select count(*) from bat3")).items[0].rows[0][0] == 0
    await pg.execute("insert into bat3 values (2)")
    await pg.commit()
    await pg.rollback()
    assert (await pg.execute("select count(*) from bat3")).items[0].rows[0][0] == 1
    await pg.set_autocommit(True)


async def test_pg_error_in_manual_tx_then_recover(pg):
    await pg.set_autocommit(False)
    with pytest.raises(DbError):
        await pg.execute("select 1/0")
    await pg.rollback()  # aborted tx must be recoverable
    assert (await pg.execute("select 1")).items[0].rows == [(1,)]
    await pg.set_autocommit(True)


async def test_pg_notice_is_reported_as_warning(pg):
    ex = await pg.execute("do $$ begin raise notice 'hello %', 42; end $$")
    assert any("hello 42" in w for w in ex.warnings)


async def test_pg_large_result_streams_through_export_path(pg):
    def consume(cols, rows):
        return [c.name for c in cols], sum(1 for _ in rows)

    names, n = await pg.stream("select g, md5(g::text) from generate_series(1, 20000) g", consume)
    assert n == 20000 and names == ["g", "md5"]


# ---------- MySQL / MariaDB / MSSQL / ClickHouse / Oracle ----------


async def test_cross_db_dml_counts_nulls_and_unicode(db):
    k = db.kind
    # each server has its own rules for unicode literals, date literals and NULL
    text_t = {"mssql": "nvarchar(50)", "clickhouse": "Nullable(String)"}.get(k, "varchar(50)")
    date_t = "Nullable(Date)" if k == "clickhouse" else "date"
    n = "N" if k == "mssql" else ""
    day = "date '2024-02-29'" if k == "oracle" else "'2024-02-29'"
    eng = " engine=MergeTree order by id" if k == "clickhouse" else ""
    await db.execute("drop table if exists bat_u")
    await db.execute(f"create table bat_u (id int, s {text_t}, d {date_t}){eng}")
    await db.execute(f"insert into bat_u values (1, {n}'тест', null), (2, null, {day})")
    rows = (await db.execute("select id, s, d from bat_u order by id")).items[0].rows
    assert rows[0][1] == "тест" and rows[0][2] is None
    assert rows[1][1] is None and str(rows[1][2]).startswith(
        "2024-02-29"
    )  # Oracle DATE carries a time
    if k != "clickhouse":
        ex = await db.execute(f"update bat_u set s = {n}'z' where id = 1")
        assert ex.items[0].update_count == 1


async def test_cross_db_error_messages_are_readable(db):
    with pytest.raises(DbError) as ei:
        await db.execute("selec 1")
    assert str(ei.value).strip()


async def test_mssql_multi_batch_and_tx(db):
    if db.kind != "mssql":
        pytest.skip("SQL Server only")
    ex = await db.execute("select 1 as a; select 2 as b")
    assert [i.rows[0][0] for i in ex.items if i.has_rows] == [1, 2]
    await db.execute("drop table if exists bat_t")
    await db.execute("create table bat_t(a int)")
    await db.set_autocommit(False)
    await db.execute("insert into bat_t values (1)")
    await db.rollback()
    assert (await db.execute("select count(*) from bat_t")).items[0].rows[0][0] == 0
    await db.set_autocommit(True)


async def test_oracle_plsql_script_with_slash_terminators(db):
    if db.kind != "oracle":
        pytest.skip("Oracle only")
    script = """\
create or replace procedure sqlide_p(x out number) as
begin
  x := 41;
  x := x + 1;
end;
/
create or replace function sqlide_f return number is
begin
  return 7;
end;
/
begin
  null;
end;
/
select sqlide_f() as seven from dual
"""
    res = await run(db, script, "oracle")
    assert len(res) == 4
    assert res[-1].items[0].rows[0][0] == 7
