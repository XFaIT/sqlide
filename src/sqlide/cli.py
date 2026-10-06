"""Command line entry point. Thin: dispatch only, no logic."""

from __future__ import annotations

import argparse
import sys

from sqlide import __version__


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sqlide", description="Terminal SQL IDE over JDBC")
    p.add_argument("--version", action="version", version=f"sqlide {__version__}")
    sub = p.add_subparsers(dest="command")
    sub.add_parser("doctor", help="check environment (JVM, drivers, clipboard)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "doctor":
        print("sqlide doctor: not implemented yet (stage 2)")
        return 0
    print("sqlide: TUI not implemented yet (stage 5)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
