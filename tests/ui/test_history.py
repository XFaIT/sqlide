"""History: executed statements are recorded; the screen inserts or re-runs them."""

from textual.widgets import Input

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from sqlide.ui.screens.history import HistoryScreen
from tests.ui.helpers import connect_first, grids, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


async def run(pilot, console, sql):
    console.editor.text = sql
    console.editor.focus()
    await pilot.press("f5")
    await wait_for(pilot, lambda: not console.running)


async def test_runs_are_recorded_with_outcome(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("hist1")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        console = app.screen.console
        await run(pilot, console, "select 1")
        await run(pilot, console, "select nope from nowhere")
        bad, good = ws.history.search()
        assert (good.sql, good.ok, good.connection) == ("select 1", True, "h")
        assert not bad.ok and "NOWHERE" in bad.error.upper()


async def test_screen_inserts_selected_entry(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("hist2")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        console = app.screen.console
        await run(pilot, console, "select 111")
        await run(pilot, console, "select 222")
        console.editor.text = ""
        await pilot.press("alt+e")
        await wait_for(pilot, lambda: isinstance(app.screen, HistoryScreen))
        app.screen.query_one(Input).value = "111"
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(pilot, lambda: not isinstance(app.screen, HistoryScreen))
        assert console.editor.text == "select 111;"


async def test_screen_run_executes_again(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("hist3")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        console = app.screen.console
        await run(pilot, console, "select 7 as seven")
        await pilot.press("alt+e")
        await wait_for(pilot, lambda: isinstance(app.screen, HistoryScreen))
        await pilot.press("f5")
        await wait_for(pilot, lambda: not isinstance(app.screen, HistoryScreen))
        await wait_for(pilot, lambda: len(ws.history.search()) == 2 and not console.running)
        assert grids(app)[0].model.row(0) == (7,)


async def test_escape_closes_and_delete_removes(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("hist4")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        console = app.screen.console
        await run(pilot, console, "select 1")
        before = console.editor.text
        await pilot.press("alt+e")
        await wait_for(pilot, lambda: isinstance(app.screen, HistoryScreen))
        await pilot.press("alt+d")
        await pilot.pause()
        assert ws.history.search() == []
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, HistoryScreen))
        assert console.editor.text == before


async def test_alt_letter_keys_work_with_a_real_terminal_character(make_ws):
    """A terminal sends alt+e with character 'e'; the editor must not swallow it as text."""
    from textual import events

    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("hist5"))))
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        ed = app.screen.console.editor
        ed.focus()
        app.post_message(events.Key("alt+e", "e"))
        await wait_for(pilot, lambda: isinstance(app.screen, HistoryScreen))
        assert ed.text == ""
