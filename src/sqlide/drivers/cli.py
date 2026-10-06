"""`sqlide driver ...` subcommands."""

from __future__ import annotations

import argparse
import sys

from sqlide.config._toml import ConfigError
from sqlide.drivers.maven import MavenError
from sqlide.drivers.registry import DriverDef, DriverRegistry


def register(sub: argparse._SubParsersAction) -> None:
    p = sub.add_parser("driver", help="manage JDBC drivers")
    ds = p.add_subparsers(dest="driver_cmd", required=True)
    ds.add_parser("list", help="show known drivers and install state")
    ins = ds.add_parser("install", help="download a driver from Maven Central")
    ins.add_argument("id")
    ins.add_argument("--version", help="default: latest stable")
    add = ds.add_parser("add", help="add a custom driver (local jars or Maven coordinates)")
    add.add_argument("id")
    add.add_argument("--name")
    add.add_argument("--jar", action="append", default=[], help="local jar (repeatable)")
    add.add_argument("--maven", help="group:artifact[:classifier]")
    add.add_argument("--class", dest="class_name", default="", help="default: auto-detect")
    add.add_argument("--url-template", default="")
    add.add_argument("--dialect", default="generic")
    p.set_defaults(handler=run)


def run(args: argparse.Namespace) -> int:
    reg = DriverRegistry()
    try:
        return {"list": _list, "install": _install, "add": _add}[args.driver_cmd](reg, args)
    except (ConfigError, MavenError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _list(reg: DriverRegistry, _: argparse.Namespace) -> int:
    for d in reg.all().values():
        vs = reg.installed_versions(d.id)
        state = "local jars" if d.jars else (vs[-1] if vs else "-")
        print(f"{d.id:<12} {d.name:<24} {state}")
    return 0


def _install(reg: DriverRegistry, args: argparse.Namespace) -> int:
    def progress(done: int, total: int | None) -> None:
        size = f"{done / 1e6:.1f}" + (f"/{total / 1e6:.1f}" if total else "") + " MB"
        print(f"\r  {size}", end="", file=sys.stderr, flush=True)

    jar = reg.install(args.id, version=args.version, progress=progress)
    print(f"\ninstalled {jar}")
    return 0


def _add(reg: DriverRegistry, args: argparse.Namespace) -> int:
    group = artifact = ""
    classifiers = [""]
    if args.maven:
        parts = args.maven.split(":")
        if len(parts) not in (2, 3):
            raise ConfigError("--maven expects group:artifact[:classifier]")
        group, artifact = parts[0], parts[1]
        classifiers = [parts[2] if len(parts) == 3 else ""]
    reg.add_custom(
        DriverDef(
            id=args.id,
            name=args.name or args.id,
            class_name=args.class_name,
            url_template=args.url_template,
            dialect=args.dialect,
            group=group,
            artifact=artifact,
            classifiers=classifiers,
            jars=args.jar,
        )
    )
    print(f"driver '{args.id}' saved to {reg.user_file}")
    if args.maven:
        print(f"download it with: sqlide driver install {args.id}")
    return 0
