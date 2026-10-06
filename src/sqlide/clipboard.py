"""System clipboard across macOS, Linux (X11/Wayland), WSL; OSC52 as the last resort."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

Backend = tuple[str, list[str], Callable[[str], bytes]]


def _utf8(s: str) -> bytes:
    return s.encode("utf-8")


def _utf16(s: str) -> bytes:  # clip.exe reads UTF-16LE when a BOM is present
    return b"\xff\xfe" + s.encode("utf-16-le")


def is_wsl() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def backends(platform: str | None = None, wsl: bool | None = None) -> list[Backend]:
    """Installed native clipboard tools in preference order."""
    import sys

    platform = platform or sys.platform
    wsl = is_wsl() if wsl is None else wsl
    candidates: list[Backend] = []
    if platform == "darwin":
        candidates.append(("pbcopy", ["pbcopy"], _utf8))
    elif platform == "win32":
        candidates.append(("clip", ["clip"], _utf16))
    else:
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates.append(("wl-copy", ["wl-copy"], _utf8))
        if os.environ.get("DISPLAY"):
            candidates.append(("xclip", ["xclip", "-selection", "clipboard", "-i"], _utf8))
            candidates.append(("xsel", ["xsel", "--clipboard", "--input"], _utf8))
        if wsl:
            candidates.append(("clip.exe", ["clip.exe"], _utf16))
    return [c for c in candidates if shutil.which(c[1][0])]


def copy_native(text: str) -> str | None:
    """Copy via the first working tool. Returns its name, or None if none worked."""
    for name, cmd, encode in backends():
        try:
            subprocess.run(cmd, input=encode(text), check=True, timeout=5, capture_output=True)
            return name
        except (OSError, subprocess.SubprocessError):
            continue
    return None


def available() -> str:
    """Human-readable description for `sqlide doctor`."""
    found = backends()
    return found[0][0] if found else "none (falls back to OSC52 terminal escape)"
