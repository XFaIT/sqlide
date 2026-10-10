"""User key overrides: keymap.toml maps binding ids to key strings.

    [keys]
    "editor.run" = "f6"
    "main.history" = "ctrl+h,alt+e"     # several keys: comma separated

`sqlide keys` lists every id with its default. Bad entries are ignored, never fatal.
"""

from __future__ import annotations

from pathlib import Path

from sqlide.config import paths
from sqlide.config._toml import ConfigError, read_toml, write_toml


def load_keymap(path: Path | None = None) -> dict[str, str]:
    try:
        raw = read_toml(path or paths.keymap_file()).get("keys", {})
    except ConfigError:
        return {}
    if not isinstance(raw, dict):
        return {}
    return {k: v.strip() for k, v in raw.items() if isinstance(v, str) and v.strip()}


def save_override(action_id: str, keys: str | None, path: Path | None = None) -> None:
    """Set (or with keys=None remove) one override, keeping the other entries of the file."""
    path = path or paths.keymap_file()
    try:
        data = read_toml(path)
    except ConfigError:
        data = {}
    table = data.get("keys")
    table = dict(table) if isinstance(table, dict) else {}
    if keys:
        table[action_id] = keys
    else:
        table.pop(action_id, None)
    data["keys"] = table
    write_toml(path, data)
