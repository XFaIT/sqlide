"""Console files and the list of open tabs. Pure storage: no UI, no JVM.

Consoles are scratch SQL files owned by the app: ``consoles/<connection>/console_N.sql``,
autosaved. Files opened by the user are saved only on request. The tab list is kept in
``state.toml`` so the next start reopens the same tabs.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from sqlide.config import paths
from sqlide.config._toml import ConfigError, read_toml, write_toml

CONSOLE, FILE = "console", "file"


@dataclass(slots=True)
class TabState:
    kind: str  # CONSOLE | FILE
    path: str
    connection: str = ""  # intended connection name; connected lazily
    active: bool = False


def safe_dirname(name: str) -> str:
    return re.sub(r"[^\w.\-]+", "_", name).strip("._") or "_"


def write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


class ConsoleStore:
    def __init__(self, root: Path | None = None, state_file: Path | None = None) -> None:
        self.root = root or paths.consoles_dir()
        self.state_file = state_file or (paths.data_dir() / "state.toml")

    def new_console_file(self, connection: str | None) -> Path:
        """Reserve the next free ``console_N.sql`` for a connection (or no connection)."""
        folder = self.root / safe_dirname(connection or "no-connection")
        folder.mkdir(parents=True, exist_ok=True)
        n = 1
        while (folder / f"console_{n}.sql").exists():
            n += 1
        path = folder / f"console_{n}.sql"
        path.touch()
        return path

    @staticmethod
    def read(path: Path) -> tuple[str, str]:
        """(text normalised to '\\n', original newline style) so saving can restore it."""
        with path.open(encoding="utf-8", newline="") as f:
            raw = f.read()
        newline = "\r\n" if "\r\n" in raw else "\n"
        return raw.replace("\r\n", "\n").replace("\r", "\n"), newline

    @staticmethod
    def write(path: Path, text: str, newline: str = "\n") -> None:
        write_text_atomic(path, text.replace("\n", newline) if newline != "\n" else text)

    # --- tab list ---
    def load_state(self) -> list[TabState]:
        try:
            raw = read_toml(self.state_file).get("tab", [])
        except ConfigError:
            return []  # a damaged state file must never stop the app from starting
        tabs = []
        for item in raw:
            try:
                tabs.append(TabState(**item))
            except TypeError:
                continue
        return [t for t in tabs if t.kind in (CONSOLE, FILE)]

    def save_state(self, tabs: list[TabState]) -> None:
        write_toml(
            self.state_file,
            {
                "tab": [
                    {"kind": t.kind, "path": t.path, "connection": t.connection, "active": t.active}
                    for t in tabs
                ]
            },
        )
