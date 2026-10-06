import datetime as dt
from decimal import Decimal

from sqlide.db.result import Column
from sqlide.grid.model import GridModel

COLS = [Column("id", "INT", 4), Column("name", "VARCHAR", 12), Column("v", "DOUBLE", 8)]
ROWS = [(3, "bob", 1.5), (1, "Alice", None), (2, "carol", 0.5), (4, None, 2.0)]


def ids(m):
    return [m.value(i, 0) for i in range(len(m))]


def test_default_order_and_access():
    m = GridModel(COLS, ROWS)
    assert len(m) == 4 and m.total_rows == 4
    assert m.row(1) == (1, "Alice", None)
    assert m.rows(1, 2) == [ROWS[1], ROWS[2]]


def test_sort_cycle_asc_desc_none():
    m = GridModel(COLS, ROWS)
    m.cycle_sort(0)
    assert ids(m) == [1, 2, 3, 4] and m.sort_state(0) == (False, 1)
    m.cycle_sort(0)
    assert ids(m) == [4, 3, 2, 1] and m.sort_state(0) == (True, 1)
    m.cycle_sort(0)
    assert ids(m) == [3, 1, 2, 4] and m.sort_state(0) is None  # original order restored


def test_nulls_last_both_directions_and_case_insensitive_text():
    m = GridModel(COLS, ROWS)
    m.cycle_sort(1)
    assert [m.value(i, 1) for i in range(4)] == ["Alice", "bob", "carol", None]
    m.cycle_sort(1)
    assert [m.value(i, 1) for i in range(4)] == ["carol", "bob", "Alice", None]


def test_multi_column_sort_is_stable_by_priority():
    rows = [(1, "b", 1), (2, "a", 2), (3, "b", 0), (4, "a", 1)]
    m = GridModel(COLS, rows)
    m.cycle_sort(1)  # name asc
    m.cycle_sort(2, add=True)  # then v asc
    assert ids(m) == [4, 2, 3, 1]
    assert m.sort_state(1) == (False, 1) and m.sort_state(2) == (False, 2)
    m.cycle_sort(2, add=True)  # v -> desc, name stays
    assert ids(m) == [2, 4, 1, 3]


def test_plain_click_replaces_other_sort_columns():
    m = GridModel(COLS, ROWS)
    m.cycle_sort(0)
    m.cycle_sort(1)
    assert m.sort == [(1, False)]


def test_mixed_types_never_raise():
    m = GridModel(COLS[:1], [(1,), ("x",), (dt.date(2020, 1, 1),), (b"a",), (Decimal("0.5"),)])
    m.cycle_sort(0)
    assert len(m) == 5  # no TypeError; numbers first, then dates, bytes, text
    assert m.value(0, 0) == Decimal("0.5") and m.value(1, 0) == 1


def test_nan_does_not_break_sorting():
    m = GridModel(COLS[:1], [(float("nan"),), (1.0,), (-1.0,)])
    m.cycle_sort(0)
    assert len(m) == 3


def test_filter_matches_any_column_case_insensitively():
    m = GridModel(COLS, ROWS)
    m.set_filter("AL")
    assert ids(m) == [1]
    m.set_filter("")
    assert len(m) == 4
    m.set_filter("nomatch")
    assert len(m) == 0


def test_filter_matches_formatted_values():
    m = GridModel(COLS, ROWS)
    m.set_filter("<null>")
    assert sorted(ids(m)) == [1, 4]


def test_filter_and_sort_combine_and_survive_append():
    m = GridModel(COLS, ROWS)
    m.set_filter("o")  # bob, carol
    m.cycle_sort(0)
    assert ids(m) == [2, 3]
    m.append([(0, "bono", 1.0), (9, "zzz", 1.0)])
    assert ids(m) == [0, 2, 3]
    assert m.total_rows == 6


def test_append_without_sort_keeps_order():
    m = GridModel(COLS, ROWS[:2])
    m.append(ROWS[2:])
    assert ids(m) == [3, 1, 2, 4]
