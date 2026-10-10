"""Create the demo database (H2 file, password from SQLIDE_DEMO_PW) used by record.py."""

from __future__ import annotations

import asyncio
import datetime as dt
import random
import sys
from pathlib import Path

from sqlide.db.session import DbSession
from sqlide.drivers.loader import load_driver
from sqlide.drivers.registry import DriverRegistry

COUNTRIES = ["Germany", "France", "Spain", "Italy", "Poland", "Portugal"]
STATUSES = ["paid", "paid", "paid", "shipped", "refunded", "pending"]


async def main(data_dir: Path, password: str) -> None:
    reg = DriverRegistry(data_dir / "drivers", data_dir / "drivers.toml")
    if not reg.is_installed("h2"):
        reg.install("h2")
    loaded = load_driver(reg.get("h2"), reg.jar_paths("h2"))
    session = DbSession(loaded, f"jdbc:h2:{data_dir / 'shop'}", "sa", password, dialect="generic")
    await session.open()
    rnd = random.Random(7)
    await session.execute('create schema if not exists "dbt-analytics"')
    await session.execute(
        'create table if not exists "dbt-analytics".customers '
        "(id int primary key, name varchar(40), country varchar(20))"
    )
    await session.execute(
        'create table if not exists "dbt-analytics".orders (id int primary key, '
        "customer_id int, amount decimal(10,2), status varchar(12), created date)"
    )
    names = [
        "Ada",
        "Boris",
        "Chloe",
        "Dmitri",
        "Elena",
        "Farid",
        "Greta",
        "Hugo",
        "Ines",
        "Jonas",
        "Karla",
        "Liam",
    ]
    for i, name in enumerate(names, 1):
        country = rnd.choice(COUNTRIES)
        await session.execute(
            f"merge into \"dbt-analytics\".customers values ({i}, '{name}', '{country}')"
        )
    day = dt.date(2026, 9, 1)
    for i in range(1, 61):
        amount = round(rnd.uniform(9, 480), 2)
        when = day + dt.timedelta(days=rnd.randrange(40))
        await session.execute(
            f'merge into "dbt-analytics".orders values ({i}, {rnd.randint(1, len(names))}, '
            f"{amount}, '{rnd.choice(STATUSES)}', '{when}')"
        )
    await session.close()


if __name__ == "__main__":
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2]))
