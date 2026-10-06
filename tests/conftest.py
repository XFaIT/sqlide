import uuid
from pathlib import Path

import pytest

from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry

CACHE = Path(__file__).parent / ".cache"  # downloaded once, gitignored


@pytest.fixture(scope="session")
def h2():
    reg = DriverRegistry(CACHE / "drivers", CACHE / "drivers.toml")
    if not reg.is_installed("h2"):
        reg.install("h2")
    defn = reg.get("h2")
    return defn, load_driver(defn, reg.jar_paths("h2"))


@pytest.fixture
async def session(h2):
    defn, loaded = h2
    s = DbSession(loaded, f"jdbc:h2:mem:{uuid.uuid4().hex};DB_CLOSE_DELAY=-1", dialect="generic")
    await s.open()
    yield s
    await s.close()


@pytest.fixture(autouse=True)
def _isolated_user_dirs(tmp_path, monkeypatch):
    """No test may touch the real ~/.config or ~/.local/share of the developer."""
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "_cfg"))
    monkeypatch.setenv("SQLIDE_DATA_DIR", str(tmp_path / "_data"))
