"""Real end-to-end: download H2 from Maven Central, load it, run a query. Needs network + Java."""

import pytest

from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def h2(tmp_path_factory):
    root = tmp_path_factory.mktemp("sqlide")
    reg = DriverRegistry(root / "drivers", root / "drivers.toml")
    reg.install("h2")
    return load_driver(reg.get("h2"), reg.jar_paths("h2"))


def test_connect_and_query(h2):
    import jpype

    props = jpype.JClass("java.util.Properties")()
    conn = h2.driver.connect("jdbc:h2:mem:t1", props)
    try:
        rs = conn.createStatement().executeQuery("select 40 + 2 as answer")
        assert rs.next() and int(rs.getInt(1)) == 42
    finally:
        conn.close()


def test_driver_cached(h2):
    reg_defn = DriverRegistry().get("h2")
    assert reg_defn.class_name == "org.h2.Driver"
