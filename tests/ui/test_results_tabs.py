"""Result tabs: new runs keep pinned ones, buttons and keys, saved between sessions."""

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from sqlide.ui.widgets.toolbar import IconButton
from tests.ui.helpers import connect_first, console, grids, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


async def run(pilot, c, sql):
    c.editor.text = sql
    c.editor.focus()
    await pilot.press("ctrl+j")
    await wait_for(pilot, lambda: not c.running)
    await pilot.pause(0.1)


def bar_button(app, title):
    return next(b for b in app.screen.query(IconButton) if b.tool.title == title)


async def test_unpinned_results_are_replaced_pinned_ones_stay(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("pin1"))))
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        c = console(app)
        await run(pilot, c, "select 1 as a")
        await run(pilot, c, "select 2 as b")
        assert len(grids(app)) == 1  # not pinned: replaced
        await pilot.press("alt+r")  # focus the grid
        await pilot.press("p")
        assert len(c.panel.pinned_ids) == 1
        await run(pilot, c, "select 3 as c")
        assert len(grids(app)) == 2
        assert [str(t.label) for t in c.panel.tabs.query("Tab")][1].startswith("📌")
        # a third run replaces the unpinned one, the pinned stays
        await run(pilot, c, "select 4 as d")
        assert len(grids(app)) == 2
        names = {g.model.columns[0].name for g in grids(app)}
        assert names == {"B", "D"}


async def test_close_and_unpin_with_the_buttons(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("pin2"))))
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        c = console(app)
        await run(pilot, c, "select 1 as a")
        await pilot.pause(0.5)
        assert not bar_button(app, "Pin result").has_class("-off")
        await pilot.click(bar_button(app, "Pin result"))
        await wait_for(pilot, lambda: len(c.panel.pinned_ids) == 1)
        await pilot.click(bar_button(app, "Pin result"))
        await wait_for(pilot, lambda: len(c.panel.pinned_ids) == 0)
        await pilot.click(bar_button(app, "Close result"))
        await wait_for(pilot, lambda: len(grids(app)) == 0)
        assert bar_button(app, "Close result").has_class("-off")  # only the log is left


async def test_pinned_and_last_results_come_back_after_a_restart(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("pin3")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        c = console(app)
        await run(pilot, c, "select 1 as kept")
        await pilot.press("alt+r")
        await pilot.press("p")
        await run(pilot, c, "select 2 as last")
        await wait_for(pilot, lambda: len(ws.results.load(str(c.path))) == 2)
        await app.action_quit()
    app2 = SqlideApp(ws)
    async with app2.run_test(size=(140, 40)) as pilot:
        await wait_for(pilot, lambda: len(grids(app2)) == 2)
        got = {g.model.columns[0].name for g in grids(app2)}
        assert got == {"KEPT", "LAST"}
        assert len(console(app2).panel.pinned_ids) == 1


async def test_rerun_runs_the_query_again(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("pin4"))))
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        c = console(app)
        await run(pilot, c, "select 1 as a")
        c.editor.text = ""
        await pilot.pause(0.5)
        await pilot.click(bar_button(app, "Run again"))
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not c.running)
