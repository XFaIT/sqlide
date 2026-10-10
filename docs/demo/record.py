"""Record the README GIFs: drive the real sqlide in tmux, save asciicast files.

    uv run python docs/demo/record.py          # writes docs/demo/*.cast
    agg --font-family "DejaVu Sans Mono" docs/demo/start.cast docs/img/start.gif

Frames come from `tmux capture-pane`, so what you see is what sqlide really drew.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).parent
ENV = Path(os.environ.get("SQLIDE_DEMO_ENV", "/tmp/sqlide_demo_env"))
COLS, ROWS = 112, 30

DEMO_SQL = """\
-- Ctrl+J runs the statement inside the frame, Ctrl+R runs the whole file
select c.country, count(*) as orders, round(sum(o.amount), 2) as revenue
from "retail-eu".orders o
join "retail-eu".customers c on c.id = o.customer_id
where o.status <> 'refunded'
group by c.country
order by revenue desc;

select * from "retail-eu".orders where status = 'refunded';
"""


def tmux(*args: str) -> str:
    return subprocess.run(["tmux", *args], capture_output=True, text=True, check=False).stdout


class Rec:
    def __init__(self, name: str, command: str, env: dict[str, str]) -> None:
        self.name = name
        self.frames: list[tuple[float, str]] = []
        self.last = ""
        tmux("kill-session", "-t", name)
        exports = " ".join(f"{k}='{v}'" for k, v in env.items())
        tmux(
            "new-session",
            "-d",
            "-x",
            str(COLS),
            "-y",
            str(ROWS),
            "-s",
            name,
            f'env {exports} sh -c "{command}"',
        )
        self.t0 = time.monotonic()

    def snap(self) -> str:
        text = tmux("capture-pane", "-p", "-e", "-t", self.name)
        if text != self.last:
            self.last = text
            self.frames.append((time.monotonic() - self.t0, text))
        return text

    def pause(self, seconds: float) -> None:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.snap()
            time.sleep(0.08)
        self.snap()

    def wait_for(self, needle: str, timeout: float = 20.0, hold: float = 0.6) -> None:
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if needle in self.snap():
                self.pause(hold)
                return
            time.sleep(0.08)
        raise SystemExit(f"[{self.name}] never saw {needle!r}:\n{self.last}")

    def keys(self, *keys: str, hold: float = 0.5) -> None:
        tmux("send-keys", "-t", self.name, *keys)
        self.pause(hold)

    def type(self, text: str, cps: float = 16.0, hold: float = 0.4) -> None:
        for ch in text:
            tmux("send-keys", "-t", self.name, "-l", ch)
            self.pause(1.0 / cps)
        self.pause(hold)

    def save(self, path: Path) -> None:
        self.pause(1.2)
        header = {
            "version": 2,
            "width": COLS,
            "height": ROWS,
            "timestamp": int(time.time()),
            "env": {"TERM": "xterm-256color"},
        }
        with path.open("w") as f:
            f.write(json.dumps(header) + "\n")
            for t, text in self.frames:
                data = "\x1b[?25l\x1b[H\x1b[2J" + text.rstrip("\n").replace("\n", "\r\n")
                f.write(json.dumps([round(t, 3), "o", data]) + "\n")
        tmux("kill-session", "-t", self.name)
        print(f"{path}: {len(self.frames)} frames, {self.frames[-1][0]:.1f}s")


def prepare() -> dict[str, str]:
    """Fresh config + data dirs with the demo database; returns the environment to use."""
    for sub in ("cfg", "data"):
        shutil.rmtree(ENV / sub, ignore_errors=True)
    (ENV / "cfg").mkdir(parents=True)
    (ENV / "data").mkdir(parents=True)
    shutil.copytree(ROOT / "tests" / ".cache" / "drivers", ENV / "data" / "drivers")
    subprocess.run(
        ["uv", "run", "python", str(OUT / "seed.py"), str(ENV / "data"), "demo"],
        cwd=ROOT,
        check=True,
    )
    (ENV / "cfg" / "connections.toml").write_text(
        '[[connection]]\nname = "shop"\ndriver = "h2"\n'
        f'url = "jdbc:h2:{ENV / "data" / "shop"}"\nuser = "sa"\n'
        'password_ref = "${env:SQLIDE_DEMO_PW}"\nschemas = ["PUBLIC", "retail-eu"]\n'
    )
    (ENV / "demo.sql").write_text(DEMO_SQL)
    return {
        "SQLIDE_CONFIG_DIR": str(ENV / "cfg"),
        "SQLIDE_DATA_DIR": str(ENV / "data"),
        "SQLIDE_DEMO_PW": "demo",
        "TERM": "xterm-256color",
        "COLORTERM": "truecolor",
    }


def scene_query(env: dict[str, str]) -> None:
    r = Rec("demo_query", f"cd {ROOT} && uv run sqlide {ENV / 'demo.sql'}", env)
    r.pause(2.5)
    r.keys("Enter", hold=0.3)  # connect the highlighted connection
    r.wait_for("Connected: shop")
    r.keys("F6", hold=0.4)  # connections -> schema
    r.keys("F6", hold=0.4)  # -> editor
    r.keys("Down", hold=0.8)  # cursor into the first statement
    r.keys("C-j", hold=0.5)
    r.wait_for("revenue", hold=1.5)
    r.keys("C-g", hold=0.6)  # results
    r.keys("Right", "Right", "Right", hold=0.5)
    r.keys("s", hold=1.2)  # sort by the column
    r.keys("s", hold=1.2)  # and descending
    r.keys("/", hold=0.4)
    r.type("fr", hold=1.2)  # filter rows
    r.keys("Escape", hold=0.6)
    r.keys("C-c", hold=1.8)  # copy
    r.save(OUT / "query.cast")


def scene_complete(env: dict[str, str]) -> None:
    """Autocomplete across schemas (even `retail-eu`), then pinned results."""
    (ENV / "scratch.sql").write_text("")
    r = Rec("demo_complete", f"cd {ROOT} && uv run sqlide {ENV / 'scratch.sql'}", env)
    r.pause(2.5)
    r.keys("Enter", hold=0.3)
    r.wait_for("Connected: shop")
    r.keys("F6", hold=0.5)
    r.keys("F6", hold=0.5)
    r.type('select * from "retail-e', hold=1.2)
    r.keys("Tab", hold=0.6)
    r.type(".", hold=1.4)
    r.type("ord", hold=0.8)
    r.keys("Tab", hold=0.4)
    r.type(" o where o.", hold=1.4)
    r.type("am", hold=0.7)
    r.keys("Tab", hold=0.4)
    r.type(" > 400;", hold=0.6)
    r.keys("C-j", hold=0.5)
    r.wait_for("AMOUNT", hold=1.5)
    r.keys("C-g", hold=0.5)
    r.keys("p", hold=1.8)  # pin this result
    for _ in range(3):  # results -> connections -> schema -> editor
        r.keys("F6", hold=0.4)
    r.keys("C-a", "BSpace", hold=0.4)
    r.type('select status, count(*) as n from "retail-eu".orders group by status;', cps=40)
    r.keys("C-j", hold=0.5)
    r.wait_for("STATUS", hold=2.5)
    r.save(OUT / "complete.cast")


def scene_start(env: dict[str, str]) -> None:
    """Install from PyPI into a throwaway dir, check the environment, start."""
    sandbox = ENV / "install"
    shutil.rmtree(sandbox, ignore_errors=True)
    (sandbox / "bin").mkdir(parents=True)
    fresh = dict(env)
    fresh.update(
        UV_TOOL_DIR=str(sandbox / "tools"),
        UV_TOOL_BIN_DIR=str(sandbox / "bin"),
        UV_CACHE_DIR=str(sandbox / "cache"),
        PATH=f"{sandbox / 'bin'}:{os.environ['PATH']}",
        PS1="$ ",
        SQLIDE_CONFIG_DIR=str(sandbox / "cfg"),
        SQLIDE_DATA_DIR=str(sandbox / "data"),
    )
    r = Rec("demo_start", "bash --norc --noprofile", fresh)
    r.pause(1.0)
    r.type("# macOS: brew tap XFaIT/sqlide && brew install sqlide", cps=45, hold=0.2)
    r.keys("Enter", hold=0.3)
    r.type("uv tool install sqlide", cps=14, hold=0.5)
    r.keys("Enter", hold=0.5)
    r.wait_for("Installed 1 executable", timeout=120, hold=1.2)
    r.type("sqlide doctor", cps=14, hold=0.4)
    r.keys("Enter", hold=0.5)
    r.wait_for("clipboard", timeout=60, hold=2.0)
    r.type("sqlide", cps=14, hold=0.4)
    r.keys("Enter", hold=0.5)
    r.wait_for("No connections yet", timeout=30, hold=1.5)
    r.keys("C-n", hold=2.5)  # the connection form
    r.keys("Escape", hold=0.8)
    r.keys("C-q", hold=0.8)
    r.save(OUT / "start.cast")


if __name__ == "__main__":
    which = sys.argv[1:] or ["start", "query", "complete"]
    environment = prepare()
    for name in which:
        globals()[f"scene_{name}"](environment)
