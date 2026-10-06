"""Filesystem locations. Env overrides exist for tests and portable installs."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_config_path, user_data_path

APP = "sqlide"


def config_dir() -> Path:
    override = os.environ.get("SQLIDE_CONFIG_DIR")
    return Path(override) if override else user_config_path(APP)


def data_dir() -> Path:
    override = os.environ.get("SQLIDE_DATA_DIR")
    return Path(override) if override else user_data_path(APP)


def settings_file() -> Path:
    return config_dir() / "settings.toml"


def connections_file() -> Path:
    return config_dir() / "connections.toml"


def keymap_file() -> Path:
    return config_dir() / "keymap.toml"


def drivers_file() -> Path:
    return config_dir() / "drivers.toml"


def drivers_dir() -> Path:
    return data_dir() / "drivers"


def history_db() -> Path:
    return data_dir() / "history.sqlite"


def consoles_dir() -> Path:
    return data_dir() / "consoles"
