"""Throwaway database containers. Run with: uv run pytest -m docker"""

import shutil
import subprocess
import time
import uuid
from pathlib import Path

import pytest

from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry

CACHE = Path(__file__).parents[1] / ".cache"


def _docker(*args: str) -> str:
    return subprocess.run(["docker", *args], capture_output=True, text=True, check=True).stdout


@pytest.fixture(scope="session")
def pg_url():
    if not shutil.which("docker"):
        pytest.skip("docker not available")
    name = f"sqlide-test-pg-{uuid.uuid4().hex[:8]}"
    _docker(
        "run",
        "-d",
        "--rm",
        "--name",
        name,
        "-e",
        "POSTGRES_PASSWORD=pw",
        "-p",
        "127.0.0.1::5432",
        "postgres:16-alpine",
    )
    try:
        port = _docker("port", name, "5432/tcp").split(":")[-1].strip()
        for _ in range(60):
            r = subprocess.run(
                ["docker", "exec", name, "pg_isready", "-U", "postgres"], capture_output=True
            )
            if r.returncode == 0:
                break
            time.sleep(1)
        else:
            pytest.fail("postgres did not become ready")
        time.sleep(1)  # pg_isready can be true during the init restart
        yield f"jdbc:postgresql://127.0.0.1:{port}/postgres"
    finally:
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)


@pytest.fixture
async def pg(pg_url):
    reg = DriverRegistry(CACHE / "drivers", CACHE / "drivers.toml")
    if not reg.is_installed("postgres"):
        reg.install("postgres")
    defn = reg.get("postgres")
    s = DbSession(
        load_driver(defn, reg.jar_paths("postgres")), pg_url, "postgres", "pw", dialect="postgres"
    )
    await s.open()
    yield s
    await s.close()
