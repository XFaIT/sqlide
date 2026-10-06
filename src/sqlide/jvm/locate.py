"""Find a usable JVM (Java 11+). Pure Python, does not start anything."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

MIN_JAVA = 11

INSTALL_HINT = (
    "Java 11+ not found. Install one:\n"
    "  macOS:  brew install openjdk\n"
    "  Debian/Ubuntu/WSL:  sudo apt install openjdk-21-jre-headless\n"
    "  or set JAVA_HOME to an existing JDK/JRE."
)


class JvmNotFound(Exception):
    """No suitable JVM on this machine; str(e) is a user-facing hint."""


@dataclass(frozen=True, slots=True)
class JvmInfo:
    home: Path
    libjvm: Path
    major: int


def _libjvm(home: Path) -> Path | None:
    names = {"darwin": ("libjvm.dylib",), "win32": ("jvm.dll",)}.get(sys.platform, ("libjvm.so",))
    for sub in ("lib/server", "bin/server", "jre/lib/server"):
        for n in names:
            p = home / sub / n
            if p.is_file():
                return p
    return None


def _major(home: Path) -> int | None:
    """Parse JAVA_VERSION from the `release` file: '21.0.1' -> 21, '1.8.0_1' -> 8."""
    try:
        text = (home / "release").read_text()
    except OSError:
        return None
    m = re.search(r'JAVA_VERSION="?(\d+)(?:\.(\d+))?', text)
    if not m:
        return None
    first, second = int(m.group(1)), m.group(2)
    return int(second) if first == 1 and second else first


def _candidates() -> list[Path]:
    out: list[Path] = []
    if env := os.environ.get("JAVA_HOME"):
        out.append(Path(env))
    if java := shutil.which("java"):
        out.append(Path(java).resolve().parent.parent)
    if sys.platform == "darwin":
        try:
            r = subprocess.run(
                ["/usr/libexec/java_home"], capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                out.append(Path(r.stdout.strip()))
        except (OSError, subprocess.SubprocessError):
            pass
        # Homebrew's openjdk is keg-only: the JDK sits under libexec, and is not on PATH
        for prefix in (Path("/opt/homebrew/opt/openjdk"), Path("/usr/local/opt/openjdk")):
            out += [prefix / "libexec/openjdk.jdk/Contents/Home", prefix]
    elif sys.platform.startswith("linux"):
        out += [Path("/home/linuxbrew/.linuxbrew/opt/openjdk")]
    return out


def locate_jvm() -> JvmInfo:
    """First candidate that has a libjvm and is Java >= MIN_JAVA."""
    seen: set[Path] = set()
    too_old: list[str] = []
    for home in _candidates():
        if home in seen:
            continue
        seen.add(home)
        lib, major = _libjvm(home), _major(home)
        if lib is None:
            continue
        if major is not None and major < MIN_JAVA:
            too_old.append(f"{home} (Java {major})")
            continue
        return JvmInfo(home=home, libjvm=lib, major=major or 0)
    msg = INSTALL_HINT
    if too_old:
        msg = f"Found only too old Java: {', '.join(too_old)}.\n{msg}"
    raise JvmNotFound(msg)
