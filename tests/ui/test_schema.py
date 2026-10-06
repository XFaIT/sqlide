"""Schema tree: lazy loading, select/insert actions."""

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from tests.ui.helpers import connect_first, grids, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


def labels(node):
    return [str(c.label) for c in node.children]


async def prepare(pilot, app):
    await connect_first(pilot, app)
    console = app.screen.console
    await console.session.execute("create schema app")
    await console.session.execute("create table app.users (id int primary key, name varchar(9))")
    console.meta.refresh()
    app.screen.schema.action_refresh()
    return console, app.screen.schema


async def test_tree_loads_lazily(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("tree1"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, tree = await prepare(pilot, app)
        await wait_for(pilot, lambda: any("APP" in t for t in labels(tree.root)))
        app_node = next(n for n in tree.root.children if "APP" in str(n.label))
        assert not app_node.children  # not loaded until expanded
        app_node.expand()
        await wait_for(pilot, lambda: any("USERS" in t for t in labels(app_node)))
        users = app_node.children[0]
        users.expand()
        await wait_for(pilot, lambda: any("NAME" in t for t in labels(users)))
        assert "ID" in labels(users)[0] and "NAME" in labels(users)[1]


async def test_enter_on_table_runs_select(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("tree2"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, tree = await prepare(pilot, app)
        await wait_for(pilot, lambda: any("APP" in t for t in labels(tree.root)))
        app_node = next(n for n in tree.root.children if "APP" in str(n.label))
        app_node.expand()
        await wait_for(pilot, lambda: any("USERS" in t for t in labels(app_node)))
        tree.focus()
        tree.move_cursor(app_node.children[0])
        await pilot.press("enter")
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not console.running)
        assert console.editor.text == "SELECT * FROM APP.USERS LIMIT 100;"
        assert grids(app)[0].model.columns[0].name == "ID"


async def test_i_inserts_name_at_cursor(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("tree3"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, tree = await prepare(pilot, app)
        await wait_for(pilot, lambda: any("APP" in t for t in labels(tree.root)))
        app_node = next(n for n in tree.root.children if "APP" in str(n.label))
        app_node.expand()
        await wait_for(pilot, lambda: any("USERS" in t for t in labels(app_node)))
        console.editor.text = "select * from "
        console.editor.move_cursor(console.editor.document.end)
        tree.focus()
        tree.move_cursor(app_node.children[0])
        await pilot.press("i")
        await pilot.pause()
        assert console.editor.text == "select * from APP.USERS"


async def test_tree_empty_when_disconnected(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.pause()
        assert str(app.screen.schema.root.label) == "not connected"
