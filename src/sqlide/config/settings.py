"""User settings. Unknown keys in the file are ignored; bad values fall back to defaults."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from pathlib import Path

from sqlide.config import paths
from sqlide.config._toml import read_toml, write_toml


@dataclass(slots=True)
class Settings:
    fetch_size: int = 500  # rows per page
    split_on_blank_line: bool = True  # blank line ends a statement (DataGrip-like)
    autosave_consoles: bool = True
    theme: str = "textual-dark"
    history_limit: int = 5000


def load_settings(path: Path | None = None) -> Settings:
    raw = read_toml(path or paths.settings_file())
    defaults = Settings()
    values = {}
    for f in fields(Settings):
        if f.name in raw and type(raw[f.name]) is type(getattr(defaults, f.name)):
            values[f.name] = raw[f.name]
    return Settings(**values)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    write_toml(path or paths.settings_file(), asdict(settings))
