"""PR guard: branch name `<version>/<slug>`, version bumped above the base branch.

Usage: check_version.py <branch> <base-ref>   (e.g. 0.3.1/fix-x origin/main)
"""

import re
import subprocess
import sys
import tomllib
from pathlib import Path

BRANCH = re.compile(r"^(\d+)\.(\d+)\.(\d+)/[a-z0-9][a-z0-9._-]*$")


def parse(v: str) -> tuple[int, int, int]:
    m = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", v)
    if not m:
        raise SystemExit(f"version {v!r} is not X.Y.Z")
    return int(m[1]), int(m[2]), int(m[3])


def main(branch: str, base: str) -> int:
    errors: list[str] = []
    m = BRANCH.match(branch)
    if not m:
        errors.append(f"branch {branch!r} must look like 0.3.1/short-description")
    current = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    init = re.search(r'__version__ = "([^"]+)"', Path("src/sqlide/__init__.py").read_text())
    if not init or init[1] != current:
        errors.append(f"__init__.__version__ ({init and init[1]}) != pyproject version ({current})")
    old_toml = subprocess.run(
        ["git", "show", f"{base}:pyproject.toml"], capture_output=True, text=True, check=True
    ).stdout
    old = tomllib.loads(old_toml)["project"]["version"]
    if m and branch.split("/")[0] != current:
        errors.append(f"branch version {branch.split('/')[0]} != pyproject version {current}")
    if parse(current) <= parse(old):
        errors.append(f"version {current} must be greater than {old} on {base} (no downgrade)")
    tags = subprocess.run(
        ["git", "tag", "--list", "v*"], capture_output=True, text=True, check=True
    ).stdout.split()
    released = [parse(t[1:]) for t in tags if re.fullmatch(r"v\d+\.\d+\.\d+", t)]
    if released and parse(current) <= max(released):
        errors.append(f"version {current} is not above the latest released tag")
    for e in errors:
        print(f"::error::{e}")
    if not errors:
        print(f"ok: {branch}, {old} -> {current}")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
