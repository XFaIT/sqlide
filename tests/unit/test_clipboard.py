import subprocess

from sqlide import clipboard


def fake_which(*present):
    return lambda name: f"/bin/{name}" if name in present else None


def names(**kw):
    return [b[0] for b in clipboard.backends(**kw)]


def test_macos(monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", fake_which("pbcopy", "xclip"))
    assert names(platform="darwin", wsl=False) == ["pbcopy"]


def test_wsl_prefers_wayland_then_falls_back_to_clip_exe(monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", fake_which("wl-copy", "clip.exe"))
    monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
    monkeypatch.delenv("DISPLAY", raising=False)
    assert names(platform="linux", wsl=True) == ["wl-copy", "clip.exe"]
    monkeypatch.setattr(clipboard.shutil, "which", fake_which("clip.exe"))
    assert names(platform="linux", wsl=True) == ["clip.exe"]


def test_linux_x11_and_headless(monkeypatch):
    monkeypatch.setattr(clipboard.shutil, "which", fake_which("xclip", "xsel"))
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    monkeypatch.setenv("DISPLAY", ":0")
    assert names(platform="linux", wsl=False) == ["xclip", "xsel"]
    monkeypatch.delenv("DISPLAY")
    assert names(platform="linux", wsl=False) == []


def test_clip_exe_gets_utf16_with_bom():
    assert (
        clipboard._utf16("é").startswith(b"\xff\xfe") and clipboard._utf16("é")[2:] == b"\xe9\x00"
    )


def test_copy_native_tries_next_backend_on_failure(monkeypatch):
    calls = []
    monkeypatch.setattr(
        clipboard,
        "backends",
        lambda: [("bad", ["bad"], clipboard._utf8), ("good", ["good"], clipboard._utf8)],
    )

    def run(cmd, input, **kw):
        calls.append((cmd[0], input))
        if cmd[0] == "bad":
            raise subprocess.CalledProcessError(1, cmd)

    monkeypatch.setattr(clipboard.subprocess, "run", run)
    assert clipboard.copy_native("héllo") == "good"
    assert calls == [("bad", "héllo".encode()), ("good", "héllo".encode())]


def test_copy_native_none_when_nothing_available(monkeypatch):
    monkeypatch.setattr(clipboard, "backends", lambda: [])
    assert clipboard.copy_native("x") is None


def test_windows_uses_clip(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "C:/Windows/System32/clip.exe")
    assert [b[0] for b in clipboard.backends(platform="win32", wsl=False)] == ["clip"]
