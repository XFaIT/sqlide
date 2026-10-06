"""Driver definitions (built-in catalog + user drivers.toml) and what is installed on disk."""

from __future__ import annotations

import shutil
import tomllib
from collections.abc import Callable
from dataclasses import dataclass, field, fields
from importlib import resources
from pathlib import Path

from sqlide.config import paths
from sqlide.config._toml import ConfigError, read_toml, write_toml
from sqlide.drivers.maven import MavenClient, MavenError, version_key


@dataclass(slots=True)
class DriverDef:
    id: str
    name: str
    class_name: str = ""  # empty = detect from META-INF/services in the jars
    url_template: str = ""
    default_port: int = 0
    dialect: str = "generic"
    group: str = ""  # Maven coordinates (downloadable driver)...
    artifact: str = ""
    classifiers: list[str] = field(default_factory=lambda: [""])
    version_suffix: str = ""
    jars: list[str] = field(default_factory=list)  # ...or local jar paths (custom driver)

    @property
    def is_maven(self) -> bool:
        return bool(self.group and self.artifact)


def _from_dict(raw: dict, origin: str) -> DriverDef:
    known = {f.name for f in fields(DriverDef)}
    if extra := set(raw) - known:
        raise ConfigError(f"{origin}: unknown driver keys {sorted(extra)}")
    try:
        d = DriverDef(**raw)
    except TypeError as e:
        raise ConfigError(f"{origin}: {e}") from e
    if not d.is_maven and not d.jars:
        raise ConfigError(f"{origin}: driver '{d.id}' needs group+artifact or jars")
    return d


def _builtin() -> dict[str, DriverDef]:
    text = resources.files("sqlide.drivers").joinpath("catalog.toml").read_text("utf-8")
    items = tomllib.loads(text)["driver"]
    return {d["id"]: _from_dict(d, "catalog.toml") for d in items}


class DriverRegistry:
    def __init__(self, drivers_dir: Path | None = None, user_file: Path | None = None) -> None:
        self.dir = drivers_dir or paths.drivers_dir()
        self.user_file = user_file or paths.drivers_file()

    # --- definitions ---
    def _user(self) -> dict[str, DriverDef]:
        items = read_toml(self.user_file).get("driver", [])
        return {d["id"]: _from_dict(d, str(self.user_file)) for d in items if "id" in d}

    def all(self) -> dict[str, DriverDef]:
        return {**_builtin(), **self._user()}  # user entry overrides built-in by id

    def get(self, driver_id: str) -> DriverDef:
        try:
            return self.all()[driver_id]
        except KeyError:
            raise ConfigError(f"unknown driver '{driver_id}'") from None

    def add_custom(self, d: DriverDef) -> None:
        _from_dict({f.name: getattr(d, f.name) for f in fields(d)}, "new driver")  # validate
        users = {**self._user(), d.id: d}
        write_toml(
            self.user_file,
            {"driver": [{f.name: getattr(u, f.name) for f in fields(u)} for u in users.values()]},
        )

    # --- disk state ---
    def installed_versions(self, driver_id: str) -> list[str]:
        root = self.dir / driver_id
        if not root.is_dir():
            return []
        vs = [p.name for p in root.iterdir() if p.is_dir() and any(p.glob("*.jar"))]
        return sorted(vs, key=version_key)

    def jar_paths(self, driver_id: str) -> list[Path]:
        d = self.get(driver_id)
        if d.jars:
            return [Path(j).expanduser() for j in d.jars if Path(j).expanduser().is_file()]
        versions = self.installed_versions(driver_id)
        return sorted((self.dir / driver_id / versions[-1]).glob("*.jar")) if versions else []

    def is_installed(self, driver_id: str) -> bool:
        return bool(self.jar_paths(driver_id))

    # --- install ---
    def install(
        self,
        driver_id: str,
        maven: MavenClient | None = None,
        version: str | None = None,
        progress: Callable[[int, int | None], None] | None = None,
    ) -> Path:
        d = self.get(driver_id)
        if not d.is_maven:
            raise MavenError(f"driver '{driver_id}' is local-jar only, nothing to download")
        maven = maven or MavenClient()
        version = version or maven.latest(d.group, d.artifact, d.version_suffix)
        url, name = maven.find_jar_url(d.group, d.artifact, version, d.classifiers)
        return maven.download(url, self.dir / driver_id / version / name, progress)

    def uninstall(self, driver_id: str) -> None:
        shutil.rmtree(self.dir / driver_id, ignore_errors=True)
