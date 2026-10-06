import zipfile

import pytest
from test_maven import make_client  # noqa: E402  (tests dir is on sys.path via rootdir)

from sqlide.config._toml import ConfigError
from sqlide.drivers.loader import DriverError, scan_driver_classes
from sqlide.drivers.registry import DriverDef, DriverRegistry


@pytest.fixture
def reg(tmp_path):
    return DriverRegistry(tmp_path / "drivers", tmp_path / "drivers.toml")


def make_jar(path, services: str | None):
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("a.txt", "x")
        if services is not None:
            z.writestr("META-INF/services/java.sql.Driver", services)
    return path


def test_builtin_catalog_has_defaults(reg):
    ids = reg.all()
    assert {"postgres", "clickhouse"} <= set(ids)
    assert ids["clickhouse"].classifiers == ["all-dependencies", "all"]


def test_unknown_driver(reg):
    with pytest.raises(ConfigError):
        reg.get("nope")


def test_custom_driver_overrides_and_persists(reg, tmp_path):
    jar = make_jar(tmp_path / "my.jar", "com.x.Drv\n")
    reg.add_custom(DriverDef(id="mine", name="Mine", jars=[str(jar)]))
    reg.add_custom(DriverDef(id="postgres", name="PG pinned", group="g", artifact="a"))
    fresh = DriverRegistry(reg.dir, reg.user_file)
    assert fresh.get("mine").jars == [str(jar)]
    assert fresh.get("postgres").name == "PG pinned"
    assert fresh.jar_paths("mine") == [jar]


def test_custom_driver_needs_source(reg):
    with pytest.raises(ConfigError):
        reg.add_custom(DriverDef(id="x", name="x"))


def test_unknown_keys_rejected(reg):
    reg.user_file.write_text('[[driver]]\nid="x"\nname="x"\njars=["a"]\nbogus=1\n')
    with pytest.raises(ConfigError, match="bogus"):
        reg.all()


def test_install_picks_stable_and_classifier(reg):
    path = reg.install("clickhouse", maven=make_client())
    assert path.parent.name == "0.10.0"
    assert reg.installed_versions("clickhouse") == ["0.10.0"]
    assert reg.is_installed("clickhouse")
    reg.uninstall("clickhouse")
    assert not reg.is_installed("clickhouse")


def test_local_only_driver_cannot_install(reg):
    reg.add_custom(DriverDef(id="loc", name="loc", jars=["/nope.jar"]))
    with pytest.raises(Exception, match="local-jar"):
        reg.install("loc")


def test_scan_driver_classes(tmp_path):
    a = make_jar(tmp_path / "a.jar", "# comment\ncom.x.A\n\ncom.x.B  # tail\n")
    b = make_jar(tmp_path / "b.jar", None)
    assert scan_driver_classes([a, b]) == ["com.x.A", "com.x.B"]


def test_scan_bad_zip(tmp_path):
    bad = tmp_path / "bad.jar"
    bad.write_text("not a zip")
    with pytest.raises(DriverError):
        scan_driver_classes([bad])
