"""Build and validate a user-defined driver (shared by the CLI and the driver manager UI)."""

from __future__ import annotations

import re
from pathlib import Path

from sqlide.config._toml import ConfigError
from sqlide.drivers.loader import DriverError, scan_driver_classes
from sqlide.drivers.registry import DriverDef

_ID = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


def parse_maven(coords: str) -> tuple[str, str, list[str]]:
    """'group:artifact[:classifier]' -> (group, artifact, classifiers)."""
    parts = [p.strip() for p in coords.split(":")]
    if len(parts) not in (2, 3) or not all(parts[:2]):
        raise ConfigError("Maven coordinates: group:artifact[:classifier]")
    return parts[0], parts[1], [parts[2] if len(parts) == 3 else ""]


def build_custom_driver(
    id: str,
    name: str = "",
    *,
    maven: str = "",
    jars: list[str] | None = None,
    class_name: str = "",
    url_template: str = "",
    default_port: int = 0,
    dialect: str = "generic",
) -> DriverDef:
    """Validate the pieces. Jars are checked on disk and the driver class is detected from them."""
    id = id.strip()
    if not _ID.match(id):
        raise ConfigError("Id: lowercase letters, digits, '-' and '_'")
    jars = [j.strip() for j in (jars or []) if j.strip()]
    if bool(maven.strip()) == bool(jars):
        raise ConfigError("Give either Maven coordinates or jar files")
    group = artifact = ""
    classifiers = [""]
    if maven.strip():
        group, artifact, classifiers = parse_maven(maven)
    resolved = [Path(j).expanduser() for j in jars]
    for j in resolved:
        if not j.is_file():
            raise ConfigError(f"No such jar: {j}")
    class_name = class_name.strip()
    if resolved and not class_name:
        try:
            found = scan_driver_classes(resolved)
        except DriverError as e:
            raise ConfigError(str(e)) from e
        if not found:
            raise ConfigError("No JDBC driver found in the jars: enter the driver class")
        class_name = found[0]
    return DriverDef(
        id=id,
        name=name.strip() or id,
        class_name=class_name,
        url_template=url_template.strip(),
        default_port=default_port,
        dialect=dialect,
        group=group,
        artifact=artifact,
        classifiers=classifiers,
        jars=[str(j) for j in resolved],
    )
