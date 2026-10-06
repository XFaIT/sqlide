import os
import sys

import pytest

from sqlide.config import paths
from sqlide.config._toml import ConfigError, read_toml
from sqlide.config.connections import Connection, ConnectionStore
from sqlide.config.secrets import PasswordResolver
from sqlide.config.settings import Settings, load_settings, save_settings


@pytest.fixture(autouse=True)
def isolated_dirs(tmp_path, monkeypatch):
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.setenv("SQLIDE_DATA_DIR", str(tmp_path / "data"))


def test_paths_follow_env(tmp_path):
    assert paths.config_dir() == tmp_path / "cfg"
    assert paths.drivers_dir() == tmp_path / "data" / "drivers"


def test_read_missing_is_empty():
    assert read_toml(paths.settings_file()) == {}


def test_read_malformed_raises(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text("x = = 1")
    with pytest.raises(ConfigError):
        read_toml(bad)


def test_settings_roundtrip_and_fallback():
    save_settings(Settings(fetch_size=100, theme="nord"))
    s = load_settings()
    assert (s.fetch_size, s.theme) == (100, "nord")
    paths.settings_file().write_text('fetch_size = "oops"\nunknown = 1\n')
    assert load_settings() == Settings()  # wrong type + unknown key ignored


def test_connection_store_roundtrip_and_private_mode():
    store = ConnectionStore()
    store.upsert(Connection("pg", "postgres", "jdbc:postgresql://h/db", user="u"))
    store.upsert(Connection("ch", "clickhouse", "jdbc:ch://h", properties={"ssl": "true"}))
    store.upsert(Connection("pg", "postgres", "jdbc:postgresql://h2/db"))  # replace
    got = {c.name: c for c in store.load()}
    assert set(got) == {"pg", "ch"}
    assert got["pg"].url.endswith("h2/db")
    assert got["ch"].properties == {"ssl": "true"}
    if os.name != "nt":  # Windows has no POSIX modes
        assert oct(store.path.stat().st_mode & 0o777) == "0o600"
    store.remove("ch")
    assert [c.name for c in store.load()] == ["pg"]


def test_plain_password_rejected():
    with pytest.raises(ConfigError):
        Connection("x", "pg", "u", password_ref="hunter2")


def test_duplicate_names_rejected():
    c = Connection("a", "pg", "u")
    with pytest.raises(ConfigError):
        ConnectionStore().save([c, c])


def test_resolver_env(monkeypatch):
    monkeypatch.setenv("PG_PASS", "s3")
    conn = Connection("a", "pg", "u", password_ref="${env:PG_PASS}")
    assert PasswordResolver().resolve(conn, prompt=lambda c: "never") == "s3"


def test_resolver_missing_env_raises(monkeypatch):
    monkeypatch.delenv("NOPE", raising=False)
    conn = Connection("a", "pg", "u", password_ref="${env:NOPE}")
    with pytest.raises(ConfigError):
        PasswordResolver().resolve(conn, prompt=lambda c: None)


def test_resolver_cmd():
    conn = Connection("a", "pg", "u", password_cmd=f"{sys.executable} -c \"print('cmdpw')\"")
    assert PasswordResolver().resolve(conn, prompt=lambda c: None) == "cmdpw"


def test_resolver_failing_cmd_raises():
    conn = Connection("a", "pg", "u", password_cmd="definitely-not-a-command-xyz")
    with pytest.raises(ConfigError):
        PasswordResolver().resolve(conn, prompt=lambda c: None)


def test_resolver_prompt_cached_and_cancel():
    conn = Connection("a", "pg", "u")
    calls = []
    r = PasswordResolver()

    def prompt(c):
        calls.append(c.name)
        return "typed"

    assert r.resolve(conn, prompt) == "typed"
    assert r.resolve(conn, prompt) == "typed"
    assert calls == ["a"]  # second call served from cache
    r.forget("a")
    assert PasswordResolver().resolve(conn, lambda c: None) is None  # cancelled


def test_password_cmd_keeps_windows_backslashes(monkeypatch):
    import subprocess

    from sqlide.config import secrets
    from sqlide.config.connections import Connection

    seen = {}

    def fake_run(cmd, **kw):
        seen["cmd"] = cmd
        return subprocess.CompletedProcess(cmd, 0, stdout="pw\n")

    monkeypatch.setattr(secrets.subprocess, "run", fake_run)
    monkeypatch.setattr(secrets.os, "name", "nt")
    conn = Connection("c", "h2", "jdbc:h2:mem:x", password_cmd=r"C:\tools\getpw.exe --name db")
    assert secrets.PasswordResolver().lookup(conn) == "pw"
    assert seen["cmd"] == [r"C:\tools\getpw.exe", "--name", "db"]
