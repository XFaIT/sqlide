"""Command line entry point. Thin: dispatch only, no logic."""

from __future__ import annotations

import argparse
import sys

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


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if getattr(args, "handler", None):
        return args.handler(args)
    print("sqlide: TUI not implemented yet (stage 5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
