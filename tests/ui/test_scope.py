"""Choosing which schemas and tables the tree shows; the tree never refreshes by itself."""

from textual.widgets import Input, SelectionList

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from sqlide.ui.screens.scope import ScopeScreen
from tests.ui.helpers import connect_first, console, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


def labels(node):
    return [str(c.label) for c in node.children]


async def make_schemas(pilot, app, n=25):
    await connect_first(pilot, app)
    c = console(app)
    for i in range(n):
        await c.session.execute(f"create schema sc_{i:02d}")
        await c.session.execute(f"create table sc_{i:02d}.fact_a (id int)")
        await c.session.execute(f"create table sc_{i:02d}.dim_b (id int)")
    c.meta.refresh()
    app.screen.schema.action_refresh()
    return c, app.screen.schema


async def test_big_database_loads_only_the_working_schema_and_lets_you_choose(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("scope1")))
    app = SqlideApp(ws)
    async with app.run_test(size=(140, 40)) as pilot:
        c, tree = await make_schemas(pilot, app)
        await wait_for(pilot, lambda: any("hidden" in t for t in labels(tree.root)))
        shown = [t for t in labels(tree.root) if "▣" in t]
        assert len(shown) == 1 and "PUBLIC" in shown[0]

        tree.focus()
        await pilot.press("s")
        await wait_for(pilot, lambda: isinstance(app.screen, ScopeScreen))
        dlg = app.screen
        lst = dlg.query_one("#scope-list", SelectionList)
        lst.select("SC_01")
        lst.select("SC_02")
        dlg.query_one("#scope-tables", Input).value = "fact_*"
        await pilot.pause()
        dlg.action_save()
        await wait_for(pilot, lambda: not isinstance(app.screen, ScopeScreen))

        await wait_for(pilot, lambda: sum("▣" in t for t in labels(tree.root)) >= 2)
        names = " ".join(labels(tree.root))
        assert "SC_01" in names and "SC_02" in names and "SC_03" not in names
        saved = ws.store.load()[0]
        assert saved.schemas == ["PUBLIC", "SC_01", "SC_02"]  # the working schema starts ticked
        assert saved.table_filter == "fact_*"

        node = next(n for n in tree.root.children if "SC_01" in str(n.label))
        node.expand()
        await wait_for(pilot, lambda: any("FACT_A" in t for t in labels(node)))
        assert not any("DIM_B" in t for t in labels(node))
        assert any("filtered out" in t for t in labels(node))


async def test_scope_dialog_search_keeps_choices_across_filters(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("scope2"))))
    async with app.run_test(size=(140, 40)) as pilot:
        c, tree = await make_schemas(pilot, app)
        tree.action_choose_scope()
        await wait_for(pilot, lambda: isinstance(app.screen, ScopeScreen))
        dlg = app.screen
        dlg.query_one("#scope-find", Input).value = "sc_0"
        await pilot.pause()
        lst = dlg.query_one("#scope-list", SelectionList)
        assert lst.option_count == 10  # SC_00 .. SC_09
        lst.select("SC_05")
        dlg.query_one("#scope-find", Input).value = "sc_1"
        await pilot.pause()
        assert lst.option_count == 10
        lst.select("SC_11")
        dlg.query_one("#scope-find", Input).value = ""
        await pilot.pause()
        assert {"sc_05", "sc_11"} <= dlg._chosen


async def test_ddl_does_not_reload_the_tree_until_f5(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("scope3"))))
    async with app.run_test(size=(140, 40)) as pilot:
        await connect_first(pilot, app)
        tree = app.screen.schema
        c = console(app)
        await wait_for(pilot, lambda: any("PUBLIC" in t for t in labels(tree.root)))
        c.run_statements(["create schema fresh"])
        await wait_for(pilot, lambda: "F5" in str(tree.root.label))
        assert not any("FRESH" in t for t in labels(tree.root))  # nothing re-read the database
        tree.focus()
        await pilot.press("f5")
        await wait_for(pilot, lambda: any("FRESH" in t for t in labels(tree.root)))
        assert "F5" not in str(tree.root.label)
