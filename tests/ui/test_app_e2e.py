"""Drives the real app headlessly with Textual's pilot, against an in-memory H2."""

import asyncio

import pytest
from textual.widgets import DataTable, Input, RichLog

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection, ConnectionStore
from sqlide.config.settings import Settings
from sqlide.drivers.registry import DriverRegistry
from sqlide.ui.screens.dialogs import ConfirmScreen, PasswordPrompt
from sqlide.ui.screens.connection_editor import ConnectionEditor
from sqlide.ui.screens.main import MainScreen
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.workspace import Workspace
from tests.conftest import CACHE

H2_URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


@pytest.fixture
def make_ws(tmp_path, h2):
    def make(*conns: Connection, registry: DriverRegistry | None = None) -> Workspace:
        store = ConnectionStore(tmp_path / "connections.toml")
        store.save(list(conns))
        reg = registry or DriverRegistry(CACHE / "drivers", tmp_path / "drivers.toml")
        return Workspace(store, reg, settings=Settings())

    return make


async def wait_for(pilot, cond, timeout=15.0):
    for _ in range(int(timeout / 0.05)):
        if cond():
            return
        await pilot.pause(0.05)
    raise AssertionError("condition not met in time")


def console(app):
    return app.screen.console


async def connect_first(pilot, app):
    await pilot.pause()
    app.screen.sidebar.index = 0
    await pilot.press("enter")
    await wait_for(pilot, lambda: console(app).session is not None)


def grids(app):
    return list(app.screen.query(ResultGrid))


def log_text(app) -> str:
    log = app.screen.query_one("#log", RichLog)
    return "\n".join(line.text for line in log.lines)


async def test_connect_run_statement_under_cursor(make_ws):
    ws = make_ws(Connection("h2mem", "h2", H2_URL.format("e2e1")))
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        ed = console(app).editor
        assert ed.has_focus and ed.dialect == "generic"
        ed.text = "select 1 as a, 'x' as b;\n\nselect x from system_range(1, 3)"
        ed.cursor_location = (0, 3)
        await pilot.pause()
        assert ed.frame_lines == (0, 0)
        await pilot.press("f5")
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not console(app).running)
        g = grids(app)[0]
        assert g.row_count == 1 and [str(c.label) for c in g.columns.values()] == ["A", "B"]
        assert [c.plain for c in g.get_row_at(0)] == ["1", "x"]

        ed.cursor_location = (2, 5)  # second statement, found by the splitter
        await pilot.pause()
        assert ed.frame_lines == (2, 2)
        await pilot.press("ctrl+j")
        await wait_for(pilot, lambda: console(app).status.message.startswith("3 rows"))
        assert grids(app)[0].row_count == 3


async def test_error_is_reported_and_session_survives(make_ws):
    app = SqlideApp(make_ws(Connection("h2mem", "h2", H2_URL.format("e2e2"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        ed = console(app).editor
        ed.text = "selec 1"
        await pilot.press("f5")
        await wait_for(pilot, lambda: "✖" in log_text(app))
        assert not grids(app)
        ed.text = "select 2"
        await pilot.press("f5")
        await wait_for(pilot, lambda: len(grids(app)) == 1)


async def test_run_all_and_dml_count(make_ws):
    app = SqlideApp(make_ws(Connection("h2mem", "h2", H2_URL.format("e2e3"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        ed = console(app).editor
        ed.text = "create table t(a int);\ninsert into t values (1),(2);\nselect * from t"
        await pilot.press("shift+f5")
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not console(app).running)
        assert grids(app)[0].row_count == 2
        assert "2 rows affected" in log_text(app)


async def test_run_without_connection_warns(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        ed = console(app).editor
        ed.text = "select 1"
        ed.focus()
        await pilot.press("f5")
        await pilot.pause()
        assert not grids(app)
        assert "Ctrl+N" in log_text(app)  # first-run hint


async def test_new_connection_dialog_saves(make_ws, tmp_path):
    ws = make_ws()
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: isinstance(app.screen, ConnectionEditor))
        app.screen.query_one("#name", Input).value = "mine"
        app.screen.query_one("#url", Input).value = "jdbc:h2:mem:x"
        await pilot.click("#save")
        await wait_for(pilot, lambda: isinstance(app.screen, MainScreen))
        assert [c.name for c in ws.connections()] == ["mine"]
        assert len(app.screen.sidebar.children) == 1


async def test_editor_validates_empty_name(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+n")
        await wait_for(pilot, lambda: isinstance(app.screen, ConnectionEditor))
        await pilot.click("#save")
        await pilot.pause()
        assert isinstance(app.screen, ConnectionEditor)  # stays open with an error
        assert "name" in str(app.screen.query_one("#error").render()).lower()


async def test_missing_driver_offers_download_and_can_decline(make_ws, tmp_path):
    empty = DriverRegistry(tmp_path / "nodrivers", tmp_path / "d.toml")
    ws = make_ws(Connection("pg", "postgres", "jdbc:postgresql://x/y", user="u"), registry=empty)
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.screen.sidebar.index = 0
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("n")
        await wait_for(pilot, lambda: isinstance(app.screen, MainScreen))
        assert console(app).session is None


async def test_password_prompt_then_connect(make_ws):
    conn = Connection("h2pw", "h2", H2_URL.format("e2e4"), user="sa")
    ws = make_ws(conn)
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.screen.sidebar.index = 0
        await pilot.press("enter")
        await wait_for(pilot, lambda: isinstance(app.screen, PasswordPrompt))
        await pilot.press("s", "e", "c", "enter")
        await wait_for(pilot, lambda: console(app).session is not None)
        assert ws.resolver.lookup(conn) == "sec"  # remembered for the session


async def test_cancel_running_query(make_ws):
    app = SqlideApp(make_ws(Connection("h2mem", "h2", H2_URL.format("e2e5"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        ed = console(app).editor
        ed.text = "select count(*) from system_range(1, 100000000) a, system_range(1, 100000000) b"
        await pilot.press("f5")
        await wait_for(pilot, lambda: console(app).running)
        await asyncio.sleep(0.4)
        await pilot.press("ctrl+f2")
        await wait_for(pilot, lambda: not console(app).running)
        assert "Cancelled" in log_text(app)
