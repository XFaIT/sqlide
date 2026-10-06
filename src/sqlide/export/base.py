"""Exporter contract, options, registry. Formats live in sibling modules, one file each."""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlide.db.result import Column

Row = tuple[Any, ...]
PROGRESS_EVERY = 1000


class ExportCancelled(Exception):
    pass


@dataclass(slots=True)
class ExportOptions:
    header: bool = True
    delimiter: str = ","  # csv
    bom: bool = False  # csv: UTF-8 BOM, makes Excel pick the right encoding
    table_name: str = "table_name"  # sql insert
    batch_size: int = 1  # sql insert: rows per INSERT
    sheet_name: str = "Result"  # xlsx
    progress: Callable[[int], None] | None = None  # rows written so far
    should_cancel: Callable[[], bool] | None = None


class Exporter(ABC):
    name: str  # registry key, e.g. "csv"
    label: str  # shown in the UI
    extension: str  # with dot

    def write(
        self, columns: Sequence[Column], rows: Iterable[Row], path: Path, opts: ExportOptions
    ) -> int:
        """Write all rows to `path` atomically. Returns the number of rows written."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f".{path.name}.part")
        try:
            count = self._write(list(columns), tracked(rows, opts), tmp, opts)
            os.replace(tmp, path)
            return count
        finally:
            tmp.unlink(missing_ok=True)

    @abstractmethod
    def _write(
        self, columns: list[Column], rows: Iterator[Row], tmp: Path, opts: ExportOptions
    ) -> int: ...


def tracked(rows: Iterable[Row], opts: ExportOptions) -> Iterator[Row]:
    """Wrap the row stream: progress callbacks and cooperative cancellation."""
    for n, row in enumerate(rows, 1):
        if opts.should_cancel is not None and opts.should_cancel():
            raise ExportCancelled()
        yield row
        if opts.progress is not None and n % PROGRESS_EVERY == 0:
            opts.progress(n)


_REGISTRY: dict[str, Exporter] = {}


def register(cls: type[Exporter]) -> type[Exporter]:
    inst = cls()
    _REGISTRY[inst.name] = inst
    return cls


def get(name: str) -> Exporter:
    try:
        return _REGISTRY[name]
    except KeyError:
        raise KeyError(f"unknown export format '{name}'") from None


def all_exporters() -> list[Exporter]:
    return list(_REGISTRY.values())
