"""Load a JDBC driver through its own URLClassLoader (no DriverManager, no global state)."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlide.drivers.registry import DriverDef
from sqlide.jvm.runtime import ensure_jvm

SERVICE_FILE = "META-INF/services/java.sql.Driver"


class DriverError(Exception):
    pass


def scan_driver_classes(jars: list[Path]) -> list[str]:
    """Driver classes declared in the jars. Pure zip read, JVM not needed."""
    found: list[str] = []
    for jar in jars:
        try:
            with zipfile.ZipFile(jar) as z:
                if SERVICE_FILE in z.namelist():
                    for line in z.read(SERVICE_FILE).decode("utf-8", "replace").splitlines():
                        line = line.split("#", 1)[0].strip()
                        if line and line not in found:
                            found.append(line)
        except (OSError, zipfile.BadZipFile) as e:
            raise DriverError(f"{jar}: {e}") from e
    return found


@dataclass(frozen=True, slots=True)
class LoadedDriver:
    driver: Any  # java.sql.Driver
    loader: Any  # java.net.URLClassLoader, set as thread context loader by sessions


_cache: dict[tuple[str, ...], LoadedDriver] = {}


def load_driver(defn: DriverDef, jars: list[Path]) -> LoadedDriver:
    if not jars:
        raise DriverError(f"driver '{defn.id}' has no jars; run: sqlide driver install {defn.id}")
    key = (defn.class_name, *map(str, jars))
    if key in _cache:
        return _cache[key]

    class_name = defn.class_name
    if not class_name:
        classes = scan_driver_classes(jars)
        if len(classes) != 1:
            raise DriverError(
                f"driver '{defn.id}': cannot pick class automatically, candidates: {classes}"
            )
        class_name = classes[0]

    ensure_jvm()
    import jpype  # deferred: JVM must be up before JClass lookups

    File, URL = jpype.JClass("java.io.File"), jpype.JClass("java.net.URL")
    jarray: Any = jpype.JArray  # JPype stubs type this too narrowly
    urls = jarray(URL)([File(str(j)).toURI().toURL() for j in jars])
    parent = jpype.JClass("java.lang.ClassLoader").getSystemClassLoader()
    loader = jpype.JClass("java.net.URLClassLoader")(urls, parent)
    try:
        cls = jpype.JClass("java.lang.Class").forName(class_name, True, loader)
        driver = cls.getDeclaredConstructor().newInstance()
    except Exception as e:  # java exceptions surface as Python exceptions in JPype
        raise DriverError(f"cannot load {class_name}: {e}") from e
    _cache[key] = LoadedDriver(driver, loader)
    return _cache[key]
