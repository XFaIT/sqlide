"""System clipboard across macOS, Linux (X11/Wayland), WSL; OSC52 as the last resort."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

Backend = tuple[str, list[str], Callable[[str], bytes]]

# clip.exe garbles non-ASCII text (and turns a UTF-16 BOM into "?"), so on WSL PowerShell moves
# the text, with UTF-8 stated explicitly on both pipes.
_PS_COPY = (
    "[Console]::InputEncoding=[Text.Encoding]::UTF8; "
    "Set-Clipboard -Value ([Console]::In.ReadToEnd())"
)
_PS_PASTE = (
    "[Console]::OutputEncoding=[Text.Encoding]::UTF8; [Console]::Out.Write((Get-Clipboard -Raw))"
)


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
        if wsl:  # WSLg's wl-copy does not always reach Windows; PowerShell always does
            candidates.append(
                ("powershell.exe", ["powershell.exe", "-NoProfile", "-Command", _PS_COPY], _utf8)
            )
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates.append(("wl-copy", ["wl-copy"], _utf8))
        if os.environ.get("DISPLAY"):
            candidates.append(("xclip", ["xclip", "-selection", "clipboard", "-i"], _utf8))
            candidates.append(("xsel", ["xsel", "--clipboard", "--input"], _utf8))
        if wsl:
            candidates.append(("clip.exe", ["clip.exe"], _utf16))  # last resort, ASCII only
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


PasteBackend = tuple[str, list[str]]


def paste_backends(platform: str | None = None, wsl: bool | None = None) -> list[PasteBackend]:
    """Installed native tools that print the clipboard, in preference order."""
    import sys

    platform = platform or sys.platform
    wsl = is_wsl() if wsl is None else wsl
    candidates: list[PasteBackend] = []
    if platform == "darwin":
        candidates.append(("pbpaste", ["pbpaste"]))
    elif platform == "win32":
        candidates.append(("powershell", ["powershell", "-NoProfile", "-Command", "Get-Clipboard"]))
    else:
        if wsl:
            candidates.append(
                ("powershell.exe", ["powershell.exe", "-NoProfile", "-Command", _PS_PASTE])
            )
        if os.environ.get("WAYLAND_DISPLAY"):
            candidates.append(("wl-paste", ["wl-paste", "-n"]))
        if os.environ.get("DISPLAY"):
            candidates.append(("xclip", ["xclip", "-selection", "clipboard", "-o"]))
            candidates.append(("xsel", ["xsel", "--clipboard", "--output"]))
    return [c for c in candidates if shutil.which(c[1][0])]


def paste_native() -> str | None:
    """Read the system clipboard via the first working tool; None when none worked."""
    for _, cmd in paste_backends():
        try:
            done = subprocess.run(cmd, check=True, timeout=5, capture_output=True)
        except (OSError, subprocess.SubprocessError):
            continue
        text = done.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
        text = text.replace("\r\n", "\n")
        return text
    return None


def copy(text: str, app) -> str:
    """Copy text everywhere it can go: the system clipboard, else OSC52; always the app's own
    buffer, so a paste inside sqlide works even when the terminal ignores OSC52."""
    used = copy_native(text)
    if used is None:
        app.copy_to_clipboard(text)  # OSC52 + the app's own buffer
    else:
        app._clipboard = text  # keep paste-inside-app working
    return used or "terminal clipboard"


def available() -> str:
    """Human-readable description for `sqlide doctor`."""
    found = backends()
    paste = paste_backends()
    out = found[0][0] if found else "none (falls back to OSC52 terminal escape)"
    return f"{out}; paste: {paste[0][0] if paste else 'terminal paste only'}"
