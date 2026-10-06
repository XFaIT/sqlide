"""Human-readable cell text. The only place that decides how a value looks."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

NULL_TEXT = "<null>"
_BYTES_PREVIEW = 16


def format_value(v: Any) -> str:
    if v is None:
        return NULL_TEXT
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, bytes):
        head = v[:_BYTES_PREVIEW].hex()
        return f"0x{head}" + (f"… ({len(v)} bytes)" if len(v) > _BYTES_PREVIEW else "")
    if isinstance(v, dt.datetime):
        text = v.isoformat(sep=" ")
        return text
    if isinstance(v, Decimal):
        return format(v, "f")
    if isinstance(v, float):
        return repr(v)
    return str(v).replace("\r\n", "⏎").replace("\n", "⏎").replace("\t", "⇥")


def raw_text(v: Any) -> str:
    """Full-fidelity text for copy/export: no truncation, NULL is empty."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, bytes):
        return "0x" + v.hex()
    if isinstance(v, dt.datetime):
        return v.isoformat(sep=" ")
    if isinstance(v, Decimal):
        return format(v, "f")
    return str(v)
