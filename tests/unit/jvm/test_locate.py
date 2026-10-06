import os
from pathlib import Path

from sqlide.jvm import locate


def make_jdk(home: Path, version: str = "21.0.1") -> Path:
    (home / "lib/server").mkdir(parents=True)
    (home / "bin/server").mkdir(parents=True)
    (home / "lib/server/libjvm.so").touch()
    (home / "lib/server/libjvm.dylib").touch()
    (home / "bin/server/jvm.dll").touch()
    (home / "release").write_text(f'JAVA_VERSION="{version}"\n')
    return home


def test_java_home_wins(tmp_path, monkeypatch):
    home = make_jdk(tmp_path / "jdk")
    monkeypatch.setenv("JAVA_HOME", str(home))
    assert locate.locate_jvm().home == home


def test_too_old_java_is_reported(tmp_path, monkeypatch):
    monkeypatch.setenv("JAVA_HOME", str(make_jdk(tmp_path / "old", "1.8.0_392")))
    monkeypatch.setattr("shutil.which", lambda name: None)
    only_env = [Path(os.environ["JAVA_HOME"])]  # real JDKs on the machine must not leak in
    monkeypatch.setattr(locate, "_candidates", lambda: only_env)
    try:
        locate.locate_jvm()
    except locate.JvmNotFound as e:
        assert "too old" in str(e) and "Java 8" in str(e)
    else:
        raise AssertionError("expected JvmNotFound")


def test_homebrew_keg_only_openjdk_is_found_on_macos(monkeypatch):
    monkeypatch.setattr(locate.sys, "platform", "darwin")
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        locate.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("no java_home"))
    )
    paths = [str(p) for p in locate._candidates()]
    assert "/opt/homebrew/opt/openjdk/libexec/openjdk.jdk/Contents/Home" in paths
    assert "/usr/local/opt/openjdk/libexec/openjdk.jdk/Contents/Home" in paths
