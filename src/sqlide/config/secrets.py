"""Password resolution. Order: password_cmd -> ${env:VAR} -> prompt callback.

The session cache lives in memory only and dies with the process.
"""

from __future__ import annotations

import os
import shlex
import subprocess
from collections.abc import Callable

from sqlide.config._toml import ConfigError
from sqlide.config.connections import ENV_REF, Connection

CMD_TIMEOUT_S = 10

Prompt = Callable[[Connection], str | None]  # None = user cancelled


def _split(cmd: str) -> list[str]:
    if os.name != "nt":
        return shlex.split(cmd)
    # non-POSIX split keeps the quotes around tokens; strip them like CreateProcess would
    return [
        t[1:-1] if len(t) > 1 and t[0] == t[-1] == '"' else t for t in shlex.split(cmd, posix=False)
    ]


class PasswordResolver:
    def __init__(self) -> None:
        self._cache: dict[str, str] = {}

    def lookup(self, conn: Connection) -> str | None:
        """Non-interactive sources only. None = the user has to be asked. May block (cmd)."""
        if conn.name in self._cache:
            return self._cache[conn.name]
        password = self._from_cmd(conn) or self._from_env(conn)
        if password is not None:
            self._cache[conn.name] = password
        return password

    def store(self, name: str, password: str) -> None:
        self._cache[name] = password

    def resolve(self, conn: Connection, prompt: Prompt) -> str | None:
        """Sync convenience: lookup, else ask via `prompt` (UI code uses lookup/store)."""
        password = self.lookup(conn)
        if password is None:
            password = prompt(conn)
            if password is not None:
                self.store(conn.name, password)
        return password

    def forget(self, name: str) -> None:
        self._cache.pop(name, None)

    @staticmethod
    def _from_cmd(conn: Connection) -> str | None:
        if not conn.password_cmd:
            return None
        try:
            res = subprocess.run(
                _split(conn.password_cmd),
                capture_output=True,
                text=True,
                timeout=CMD_TIMEOUT_S,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as e:
            raise ConfigError(f"{conn.name}: password_cmd failed: {e}") from e
        return res.stdout.rstrip("\r\n")

    @staticmethod
    def _from_env(conn: Connection) -> str | None:
        m = ENV_REF.match(conn.password_ref)
        if not m:
            return None
        value = os.environ.get(m.group(1))
        if value is None:
            raise ConfigError(f"{conn.name}: env var {m.group(1)} is not set")
        return value
