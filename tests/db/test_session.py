import asyncio
import datetime as dt
from decimal import Decimal

import pytest

from sqlide.db.result import DbError


async def test_types_roundtrip(session):
    await session.execute(
        "create table t(i int, b bigint, d decimal(10,2), s varchar(20), dt date, tm time,"
        " ts timestamp, f boolean, x double, bin varbinary(4))"
    )
    await session.execute(
        "insert into t values (1, 9999999999, 12.50, 'héllo', date '2026-01-02', time '10:11:12',"
        " timestamp '2026-01-02 03:04:05.123456', true, 1.5, X'cafe')"
    )
    await session.execute(
        "insert into t values (null,null,null,null,null,null,null,null,null,null)"
    )
    ex = await session.execute("select * from t order by i nulls last")
    item = ex.items[0]
    assert [c.name for c in item.columns][:3] == ["I", "B", "D"]
    assert item.rows[0] == (
        1, 9999999999, Decimal("12.50"), "héllo", dt.date(2026, 1, 2), dt.time(10, 11, 12),
        dt.datetime(2026, 1, 2, 3, 4, 5, 123456), True, 1.5, b"\xca\xfe",
    )  # fmt: skip
    assert item.rows[1] == (None,) * 10


async def test_update_counts(session):
    ex = await session.execute("create table u(a int)")
    assert ex.items[0].update_count == 0 and not ex.items[0].has_rows
    ex = await session.execute("insert into u select x from system_range(1, 7)")
    assert ex.items[0].update_count == 7


async def test_paging_with_peek(session):
    ex = await session.execute("select x from system_range(1, 1200)", page_size=500)
    item = ex.items[0]
    assert len(item.rows) == 500 and item.cursor is not None
    rows, done = await item.cursor.fetch_more(500)
    assert len(rows) == 500 and not done and rows[0] == (501,)
    rows, done = await item.cursor.fetch_more(500)
    assert len(rows) == 200 and done and rows[-1] == (1200,)


async def test_exact_page_size_has_no_cursor(session):
    ex = await session.execute("select x from system_range(1, 500)", page_size=500)
    assert len(ex.items[0].rows) == 500 and ex.items[0].cursor is None


async def test_new_execute_closes_old_cursor(session):
    first = (await session.execute("select x from system_range(1, 50)", page_size=10)).items[0]
    await session.execute("select 1")
    with pytest.raises(DbError, match="closed"):
        await first.cursor.fetch_more(10)


async def test_sql_error_is_dberror(session):
    with pytest.raises(DbError) as ei:
        await session.execute("selec 1")
    assert ei.value.sql_state and "selec" in str(ei.value).lower()
    ex = await session.execute("select 1")  # session still usable after an error
    assert ex.items[0].rows == [(1,)]


async def test_cancel(session):
    slow = "select count(*) from system_range(1, 100000000) a, system_range(1, 100000000) b"
    task = asyncio.create_task(session.execute(slow))
    await asyncio.sleep(0.5)
    session.cancel()
    with pytest.raises(DbError, match="Cancelled"):
        await asyncio.wait_for(task, 10)
    assert (await session.execute("select 2")).items[0].rows == [(2,)]


async def test_manual_transaction(session):
    await session.execute("create table tx(a int)")
    await session.set_autocommit(False)
    await session.execute("insert into tx values (1)")
    assert session.pending_tx
    await session.rollback()
    assert not session.pending_tx
    assert (await session.execute("select count(*) from tx")).items[0].rows == [(0,)]
    await session.execute("insert into tx values (1)")
    await session.commit()
    assert (await session.execute("select count(*) from tx")).items[0].rows == [(1,)]


async def test_close(session):
    await session.close()
    assert not session.connected


async def test_call_after_close_is_a_db_error_not_a_crash(session):
    await session.close()
    with pytest.raises(DbError, match="closed"):
        await session.call(lambda conn: conn)
    await session.close()  # closing twice is fine
