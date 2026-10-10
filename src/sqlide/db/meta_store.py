"""Metadata snapshots on disk: the tree and autocomplete are ready right after a restart.

One JSON file per connection (name + url), under `data_dir()/meta/`. A snapshot is only ever
replaced by newer reads; `drop()` (F5, DDL) deletes it. A bad or foreign file is ignored.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from sqlide.config import paths

VERSION = 1


class MetaDisk:
    """The snapshot file of one connection."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[str, Any] | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if isinstance(data, dict) and data.get("version") == VERSION else None

    def save(self, data: dict[str, Any]) -> None:
        """Atomic write; failures are swallowed (a cache must never break the app)."""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=f".{self.path.name}.")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump({**data, "version": VERSION}, f, ensure_ascii=False)
                os.replace(tmp, self.path)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        except OSError:
            pass

    def drop(self) -> None:
        with contextlib.suppress(OSError):
            self.path.unlink(missing_ok=True)


class MetaStore:
    def __init__(self, root: Path | None = None) -> None:
        self._root = root

    def for_connection(self, name: str, url: str) -> MetaDisk:
        root = self._root or paths.data_dir() / "meta"
        digest = hashlib.sha1(f"{name}\n{url}".encode()).hexdigest()[:10]
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:40] or "conn"
        return MetaDisk(root / f"{safe}-{digest}.json")
