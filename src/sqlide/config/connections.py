"""Saved connections. Passwords are never stored: only a reference or nothing."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlide.config import paths
from sqlide.config._toml import ConfigError, read_toml, write_toml

ENV_REF = re.compile(r"^\$\{env:([A-Za-z_][A-Za-z0-9_]*)\}$")


@dataclass(slots=True)
class Connection:
    name: str
    driver: str  # driver id, see drivers registry
    url: str  # JDBC url, e.g. jdbc:postgresql://host:5432/db
    user: str = ""
    password_ref: str = ""  # "" = ask on connect, or "${env:VAR}"
    password_cmd: str = ""  # shell-free command whose stdout is the password
    properties: dict[str, str] = field(default_factory=dict)
    autocommit: bool = True
    schemas: list[str] = field(default_factory=list)  # schemas/databases the tree shows
    table_filter: str = ""  # comma-separated globs or substrings; "" = all tables

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigError("connection name is empty")
        if self.password_ref and not ENV_REF.match(self.password_ref):
            raise ConfigError(
                f"{self.name}: password_ref must look like ${{env:VAR}}, "
                "plain passwords are not stored"
            )


class ConnectionStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or paths.connections_file()

    def load(self) -> list[Connection]:
        raw = read_toml(self.path)
        out = []
        for item in raw.get("connection", []):
            try:
                out.append(Connection(**item))
            except TypeError as e:
                raise ConfigError(f"{self.path}: bad connection entry: {e}") from e
        return out

    def save(self, connections: list[Connection]) -> None:
        names = [c.name for c in connections]
        if len(names) != len(set(names)):
            raise ConfigError("duplicate connection names")
        data: dict[str, Any] = {"connection": [_to_dict(c) for c in connections]}
        write_toml(self.path, data, private=True)

    def upsert(self, conn: Connection) -> None:
        items = [c for c in self.load() if c.name != conn.name]
        self.save([*items, conn])

    def remove(self, name: str) -> None:
        self.save([c for c in self.load() if c.name != name])


def _to_dict(c: Connection) -> dict[str, Any]:
    return {
        "name": c.name,
        "driver": c.driver,
        "url": c.url,
        "user": c.user,
        "password_ref": c.password_ref,
        "password_cmd": c.password_cmd,
        "properties": c.properties,
        "autocommit": c.autocommit,
        "schemas": c.schemas,
        "table_filter": c.table_filter,
    }
