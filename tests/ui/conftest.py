import pytest

from sqlide.config.connections import Connection, ConnectionStore
from sqlide.config.settings import Settings
from sqlide.drivers.registry import DriverRegistry
from sqlide.workspace import Workspace
from tests.conftest import CACHE


@pytest.fixture
def make_ws(tmp_path, h2):
    """Build a Workspace on temp dirs, with the cached H2 driver available."""

    def make(*conns: Connection, registry: DriverRegistry | None = None) -> Workspace:
        store = ConnectionStore(tmp_path / "connections.toml")
        store.save(list(conns))
        reg = registry or DriverRegistry(CACHE / "drivers", tmp_path / "drivers.toml")
        return Workspace(store, reg, settings=Settings())

    return make
