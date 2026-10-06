"""JDBC value -> Python value. Values stay typed so sorting and xlsx export are correct."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from decimal import Decimal
from typing import Any

# java.sql.Types constants (stable by spec)
BIT, TINYINT, SMALLINT, INTEGER, BIGINT = -7, -6, 5, 4, -5
FLOAT, REAL, DOUBLE, NUMERIC, DECIMAL = 6, 7, 8, 2, 3
DATE, TIME, TIMESTAMP, BOOLEAN = 91, 92, 93, 16
BINARY, VARBINARY, LONGVARBINARY, BLOB = -2, -3, -4, 2004

_INTS = {TINYINT, SMALLINT, INTEGER, BIGINT}
_FLOATS = {FLOAT, REAL, DOUBLE}
_DECIMALS = {NUMERIC, DECIMAL}
_BOOLS = {BIT, BOOLEAN}
_BYTES = {BINARY, VARBINARY, LONGVARBINARY, BLOB}

Converter = Callable[[Any], Any]  # (java ResultSet) -> python value


def make_converter(index: int, jdbc_type: int) -> Converter:
    """Converter for column `index` (1-based). Any conversion failure falls back to text."""
    primary = _primary(index, jdbc_type)

    def convert(rs: Any) -> Any:
        try:
            return primary(rs)
        except Exception:  # java exceptions too: out-of-range dates, unsigned bigint, ...
            try:
                s = rs.getString(index)
                return None if s is None else str(s)
            except Exception:
                return "<unreadable>"

    return convert


def _primary(i: int, t: int) -> Converter:
    if t in _INTS:
        return lambda rs: _prim(rs, int(rs.getLong(i)))
    if t in _FLOATS:
        return lambda rs: _prim(rs, float(rs.getDouble(i)))
    if t in _BOOLS:
        return lambda rs: _prim(rs, bool(rs.getBoolean(i)))
    if t in _DECIMALS:
        return lambda rs: _obj(rs.getBigDecimal(i), lambda v: Decimal(str(v.toPlainString())))
    if t == DATE:
        return lambda rs: _obj(rs.getDate(i), lambda v: _date(v.toLocalDate()))
    if t == TIME:
        return lambda rs: _obj(rs.getTime(i), lambda v: _time(v.toLocalTime()))
    if t == TIMESTAMP:
        return lambda rs: _obj(rs.getTimestamp(i), lambda v: _datetime(v.toLocalDateTime()))
    if t in _BYTES:
        return lambda rs: _obj(rs.getBytes(i), bytes)
    return lambda rs: _obj(rs.getString(i), str)


def _prim(rs: Any, value: Any) -> Any:
    return None if rs.wasNull() else value


def _obj(value: Any, f: Callable[[Any], Any]) -> Any:
    return None if value is None else f(value)


def _date(d: Any) -> dt.date:
    return dt.date(int(d.getYear()), int(d.getMonthValue()), int(d.getDayOfMonth()))


def _time(t: Any) -> dt.time:
    return dt.time(
        int(t.getHour()), int(t.getMinute()), int(t.getSecond()), int(t.getNano()) // 1000
    )


def _datetime(v: Any) -> dt.datetime:
    return dt.datetime(
        int(v.getYear()), int(v.getMonthValue()), int(v.getDayOfMonth()),
        int(v.getHour()), int(v.getMinute()), int(v.getSecond()), int(v.getNano()) // 1000,
    )  # fmt: skip
