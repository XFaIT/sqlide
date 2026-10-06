"""Plain result containers. No JVM or UI imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


class DbError(Exception):
    def __init__(self, message: str, sql_state: str = "", vendor_code: int = 0) -> None:
        super().__init__(message)
        self.sql_state = sql_state
        self.vendor_code = vendor_code


@dataclass(frozen=True, slots=True)
class Column:
    name: str
    type_name: str
    jdbc_type: int


class RowSource(Protocol):
    """Open server-side cursor: load further pages of the same result."""

    async def fetch_more(self, n: int) -> tuple[list[tuple[Any, ...]], bool]:
        """Return (rows, done)."""
        ...

    async def close(self) -> None: ...


@dataclass(slots=True)
class ResultItem:
    """One result of a statement: either rows or an update count."""

    columns: list[Column] = field(default_factory=list)
    rows: list[tuple[Any, ...]] = field(default_factory=list)
    update_count: int | None = None
    cursor: RowSource | None = None  # set while more rows are pending

    @property
    def has_rows(self) -> bool:
        return self.update_count is None


@dataclass(slots=True)
class Execution:
    sql: str
    items: list[ResultItem]
    warnings: list[str]
    elapsed_s: float
