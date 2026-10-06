"""Tiny TOML IO shared by config modules: tolerant read, atomic write."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any

import tomli_w


class ConfigError(Exception):
    """Config file is unreadable or invalid."""


def read_toml(path: Path) -> dict[str, Any]:
    """Return {} when the file is missing; raise ConfigError when it is malformed."""
    try:
        with path.open("rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        return {}
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path}: {e}") from e


def write_toml(path: Path, data: dict[str, Any], *, private: bool = False) -> None:
    """Write atomically (temp file + rename) so a crash never leaves a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            tomli_w.dump(data, f)
        if private:
            os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
