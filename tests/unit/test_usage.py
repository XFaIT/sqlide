from sqlide.history.usage import UsageStore
from sqlide.sql.usage import extract


def keys(sql, dialect="generic"):
    return [u.key for u in extract(sql, dialect)]


def test_tables_and_qualified_columns_are_counted():
    got = keys("select o.total, c.name, x from public.orders o join cust c on c.id = o.cid")
    assert "table:public.orders" in got and "table:cust" in got
    assert "column:public.orders.total" in got and "column:cust.name" in got
    assert not any(k.endswith(".x") for k in got)  # two tables: a bare column is ambiguous


def test_bare_columns_count_when_one_table_is_certain():
    got = keys("select id, name, count(*) as n from users where age > 3")
    assert {"column:users.id", "column:users.name", "column:users.age"} <= set(got)
    assert not any(k.endswith((".select", ".count", ".n", ".where")) for k in got)


def test_cte_is_not_a_table_and_its_columns_are_not_guessed():
    got = keys("with c as (select 1 id) select id from c join users u on 1 = 1")
    assert "table:users" in got and "table:c" not in got
    assert "column:users.id" not in got


def test_hyphenated_backtick_names_in_databricks():
    got = keys("select `user-name` from `dbt-analytics`.orders", "databricks")
    assert "table:dbt-analytics.orders" in got and "column:dbt-analytics.orders.user-name" in got


def test_store_counts_decays_and_ranks(tmp_path):
    store = UsageStore(tmp_path / "u.sqlite")
    day = 86400.0
    now = 1_000 * day
    store.record("c", extract("select * from old"), ts=now - 90 * day)
    for _ in range(3):
        store.record("c", extract("select * from fresh"), ts=now)
    store.record("other", extract("select * from elsewhere"), ts=now)
    scores = store.scores("c", now)
    assert scores["table:fresh"] == 3 and scores["table:old"] < 0.2
    assert "table:elsewhere" not in scores
    assert store.top_tables("c", now=now) == [("fresh",), ("old",)]


def test_backfill_flag_and_forget(tmp_path):
    store = UsageStore(tmp_path / "u.sqlite")
    assert store.needs_backfill("c")
    store.mark_backfilled("c")
    assert not store.needs_backfill("c")
    store.record("c", extract("select * from t"))
    store.forget("c")
    assert store.scores("c") == {} and store.needs_backfill("c")
