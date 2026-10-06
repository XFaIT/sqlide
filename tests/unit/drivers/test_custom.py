import pytest
from tests.conftest import CACHE

from sqlide.config._toml import ConfigError
from sqlide.drivers.custom import build_custom_driver, parse_maven
from sqlide.drivers.registry import DriverRegistry


@pytest.fixture
def h2_jar(h2):
    return str(DriverRegistry(CACHE / "drivers", CACHE / "drivers.toml").jar_paths("h2")[0])


def test_parse_maven():
    assert parse_maven("a.b:c") == ("a.b", "c", [""])
    assert parse_maven("a.b:c:all") == ("a.b", "c", ["all"])
    with pytest.raises(ConfigError):
        parse_maven("only-one")


def test_jar_driver_detects_class(h2_jar):
    d = build_custom_driver("my-h2", "My H2", jars=[h2_jar], dialect="generic")
    assert d.class_name == "org.h2.Driver" and d.jars == [h2_jar] and not d.is_maven


def test_maven_driver():
    d = build_custom_driver("x", maven="org.foo:bar:all", class_name="org.foo.Driver")
    assert (d.group, d.artifact, d.classifiers, d.name) == ("org.foo", "bar", ["all"], "x")


@pytest.mark.parametrize(
    "kwargs",
    [
        {"id": "Bad Id", "maven": "a:b"},
        {"id": "x"},  # neither maven nor jars
        {"id": "x", "maven": "a:b", "jars": ["/some.jar"]},  # both
        {"id": "x", "jars": ["/does/not/exist.jar"]},
    ],
)
def test_rejects_bad_input(kwargs):
    with pytest.raises(ConfigError):
        build_custom_driver(**kwargs)


def test_jar_without_driver_service_asks_for_class(tmp_path):
    import zipfile

    jar = tmp_path / "empty.jar"
    with zipfile.ZipFile(jar, "w") as z:
        z.writestr("x.txt", "hi")
    with pytest.raises(ConfigError, match="driver class"):
        build_custom_driver("x", jars=[str(jar)])
    assert build_custom_driver("x", jars=[str(jar)], class_name="a.B").class_name == "a.B"
