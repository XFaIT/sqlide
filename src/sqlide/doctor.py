"""`sqlide doctor`: environment checks. Each check is independent; add new ones to CHECKS."""

from __future__ import annotations

from collections.abc import Callable

from sqlide.config import paths
from sqlide.drivers.registry import DriverRegistry
from sqlide.jvm.locate import JvmNotFound, locate_jvm

Check = Callable[[], tuple[bool, str]]


def check_jvm() -> tuple[bool, str]:
    try:
        info = locate_jvm()
    except JvmNotFound as e:
        return False, str(e)
    return True, f"Java {info.major} at {info.home}"


def check_drivers() -> tuple[bool, str]:
    reg = DriverRegistry()
    have = [d for d in reg.all() if reg.is_installed(d)]
    return bool(have), ", ".join(have) if have else "none installed: sqlide driver install postgres"


def check_dirs() -> tuple[bool, str]:
    return True, f"config {paths.config_dir()}, data {paths.data_dir()}"


CHECKS: list[tuple[str, Check]] = [
    ("java", check_jvm),
    ("drivers", check_drivers),
    ("dirs", check_dirs),
]


def run() -> int:
    bad = 0
    for label, fn in CHECKS:
        ok, detail = fn()
        bad += not ok
        print(f"[{'ok' if ok else '!!'}] {label:<8} {detail}")
    return 1 if bad else 0
