"""Throwaway containers for several databases, started on demand and removed at the end."""

from __future__ import annotations

import shutil
import socket
import subprocess
import time
import uuid
from dataclasses import dataclass

import pytest


@dataclass(frozen=True)
class Spec:
    driver: str
    image: str
    port: int
    env: tuple[str, ...]
    user: str
    password: str
    url: str  # {port} placeholder
    dialect: str
    docker_args: tuple[str, ...] = ()


SPECS = {
    "mysql": Spec(
        "mysql", "mysql:8.4", 3306, ("MYSQL_ROOT_PASSWORD=pw", "MYSQL_DATABASE=app"),
        "root", "pw", "jdbc:mysql://127.0.0.1:{port}/app", "mysql",
    ),
    "mariadb": Spec(
        "mariadb", "mariadb:11", 3306, ("MARIADB_ROOT_PASSWORD=pw", "MARIADB_DATABASE=app"),
        "root", "pw", "jdbc:mariadb://127.0.0.1:{port}/app", "mysql",
    ),
    "clickhouse": Spec(
        "clickhouse", "clickhouse/clickhouse-server:24.8", 8123, ("CLICKHOUSE_PASSWORD=pw",),
        "default", "pw", "jdbc:clickhouse://127.0.0.1:{port}/default", "clickhouse",
    ),
    "mssql": Spec(
        "mssql", "mcr.microsoft.com/mssql/server:2022-latest", 1433,
        ("ACCEPT_EULA=Y", "MSSQL_SA_PASSWORD=Sqlide#Pw123"),
        "sa", "Sqlide#Pw123",
        "jdbc:sqlserver://127.0.0.1:{port};databaseName=master;encrypt=false", "mssql",
    ),
    "oracle": Spec(
        "oracle", "gvenzl/oracle-free:slim-faststart", 1521, ("ORACLE_PASSWORD=pw",),
        "system", "pw", "jdbc:oracle:thin:@//127.0.0.1:{port}/FREEPDB1", "oracle",
    ),
}  # fmt: skip


def _docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout


class Containers:
    def __init__(self) -> None:
        self._names: dict[str, str] = {}
        self._ports: dict[str, int] = {}

    def url(self, kind: str) -> str:
        spec = SPECS[kind]
        if kind not in self._names:
            if not shutil.which("docker"):
                pytest.skip("docker not available")
            name = f"sqlide-test-{kind}-{uuid.uuid4().hex[:6]}"
            args = ["run", "-d", "--rm", "--name", name, "-p", f"127.0.0.1::{spec.port}"]
            for e in spec.env:
                args += ["-e", e]
            _docker(*args, spec.image)
            self._names[kind] = name
            self._ports[kind] = int(_docker("port", name, f"{spec.port}/tcp").split(":")[-1])
            self._wait_tcp(self._ports[kind])
        return spec.url.format(port=self._ports[kind])

    @staticmethod
    def _wait_tcp(port: int, timeout: float = 120) -> None:
        end = time.time() + timeout
        while time.time() < end:
            try:
                socket.create_connection(("127.0.0.1", port), 1).close()
                return
            except OSError:
                time.sleep(1)
        pytest.fail("container port never opened")

    def close(self) -> None:
        for name in self._names.values():
            subprocess.run(["docker", "rm", "-f", name], capture_output=True)
