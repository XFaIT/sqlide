import datetime as dt
from decimal import Decimal

from sqlide.db.result import Column
from sqlide.history.results import MAX_ROWS, ResultStore, SavedResult

COLS = [Column("id", "INT", 4), Column("at", "TIMESTAMP", 93)]


def saved(title="t", pinned=False, rows=None):
    return SavedResult(title, "select 1", 1.0, pinned, COLS, rows or [(1, None)])


def test_round_trip_keeps_types(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    rows = [
        (Decimal("1.50"), dt.datetime(2026, 10, 10, 12, 0, 1)),
        (dt.date(2026, 1, 2), dt.time(3, 4, 5)),
        (b"\x00\xff", None),
        (None, "ünï"),
        (True, 7),
    ]
    store.replace("c1", [saved(rows=rows, pinned=True)])
    [got] = store.load("c1")
    assert got.pinned and got.title == "t" and got.columns == COLS
    assert got.rows == rows


def test_nan_comes_back_as_nan(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    store.replace("a", [saved(rows=[(float("nan"), float("inf"))])])
    nan, inf = store.load("a")[0].rows[0]
    assert nan != nan and inf == float("inf")


def test_replace_swaps_the_consoles_tabs_only(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    store.replace("a", [saved("one"), saved("two")])
    store.replace("b", [saved("other")])
    store.replace("a", [saved("three")])
    assert [r.title for r in store.load("a")] == ["three"]
    assert [r.title for r in store.load("b")] == ["other"]
    store.forget("b")
    assert store.load("b") == []


def test_big_results_are_cut_and_flagged(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    store.replace("a", [saved(rows=[(i, None) for i in range(MAX_ROWS + 10)])])
    [got] = store.load("a")
    assert len(got.rows) == MAX_ROWS and got.truncated


def test_unknown_values_become_their_text(tmp_path):
    store = ResultStore(tmp_path / "r.sqlite")
    store.replace("a", [saved(rows=[([1, 2], {"k": 1})])])
    assert store.load("a")[0].rows == [("[1, 2]", "{'k': 1}")]
