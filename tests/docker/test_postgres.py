import datetime as dt
import uuid

import pytest

from sqlide.db.result import DbError

pytestmark = pytest.mark.docker


async def test_paging_in_autocommit_mode_streams_and_restores_autocommit(pg):
    ex = await pg.execute("select g from generate_series(1, 1200) g", page_size=500)
    item = ex.items[0]
    assert len(item.rows) == 500 and item.cursor is not None
    assert await pg.call(lambda c: not c.getAutoCommit())  # paging tx is open
    rows, done = await item.cursor.fetch_more(500)
    assert len(rows) == 500 and not done
    rows, done = await item.cursor.fetch_more(500)
    assert len(rows) == 200 and done
    assert await pg.call(lambda c: bool(c.getAutoCommit()))  # restored


async def test_ddl_and_dml_are_committed_in_autocommit_mode(pg):
    await pg.execute("create table if not exists pgt(a int)")
    await pg.execute("insert into pgt values (1)")
    other = await pg.call(lambda c: bool(c.getAutoCommit()))
    assert other
    assert (await pg.execute("select count(*) from pgt")).items[0].rows[0][0] >= 1


async def test_types(pg):
    ex = await pg.execute(
        "select now()::timestamptz, gen_random_uuid(), '{\"a\":1}'::jsonb,"
        " 1.50::numeric, array[1,2], '\\xdead'::bytea, 'infinity'::date, null::int"
    )
    row = ex.items[0].rows[0]
    assert isinstance(row[0], dt.datetime)
    assert uuid.UUID(row[1])
    assert '"a"' in row[2]
    assert str(row[3]) == "1.50"
    assert "1" in row[4] and "2" in row[4]
    assert row[5] == b"\xde\xad"
    assert isinstance(row[6], str)  # out-of-range for python date -> text fallback
    assert row[7] is None


async def test_error_rolls_back_paging_tx(pg):
    with pytest.raises(DbError) as ei:
        await pg.execute("select 1/0")
    assert ei.value.sql_state == "22012"
    assert await pg.call(lambda c: bool(c.getAutoCommit()))
    assert (await pg.execute("select 1")).items[0].rows == [(1,)]


async def test_notice_becomes_warning(pg):
    ex = await pg.execute("do $$ begin raise notice 'hello'; end $$")
    assert any("hello" in w for w in ex.warnings)
