"""Command line entry point. Thin: dispatch only, no logic."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlide import __version__
from sqlide.drivers import cli as driver_cli


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sqlide", description="Terminal SQL IDE over JDBC")
    p.add_argument("--version", action="version", version=f"sqlide {__version__}")
    sub = p.add_subparsers(dest="command")
    d = sub.add_parser("doctor", help="check environment (JVM, drivers, config dirs)")
    d.set_defaults(handler=lambda _: _doctor())
    driver_cli.register(sub)
    return p


def _doctor() -> int:
    from sqlide import doctor

    return doctor.run()


COMMANDS = {"doctor", "driver"}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] not in COMMANDS and not argv[0].startswith("-"):
        return _run_tui([Path(a) for a in argv])  # `sqlide query.sql other.sql`
    args = build_parser().parse_args(argv)
    if getattr(args, "handler", None):
        return args.handler(args)
    return _run_tui([])


def _run_tui(files: list[Path]) -> int:
    from sqlide.app import SqlideApp

    SqlideApp(files=files).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
