"""Autocomplete popup: opens on Ctrl+Space and after a dot, filters, accepts."""

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from tests.ui.helpers import connect_first, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


async def setup(pilot, app, name):
    await connect_first(pilot, app)
    console = app.screen.console
    await console.session.execute("create table people (id int, full_name varchar(9))")
    console.meta.refresh()  # created behind the cache's back
    console.editor.focus()
    await pilot.pause()
    return console, console.editor


def popup(editor):
    return editor._popup


async def type_text(pilot, text):
    for ch in text:
        await pilot.press(ch if ch != "." else "full_stop")


async def test_ctrl_space_opens_and_enter_accepts(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac1"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac1")
        await type_text(pilot, "select * from peo")
        await pilot.press("ctrl+space")
        await wait_for(pilot, lambda: ed.completing)
        assert popup(ed).current.text == "PEOPLE"
        await pilot.press("enter")
        await pilot.pause()
        assert ed.text == "select * from PEOPLE"
        assert not ed.completing


async def test_dot_opens_alias_columns_and_typing_filters(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac2"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac2")
        ed.text = "select p from people p"
        ed.move_cursor((0, 8))
        await pilot.press("full_stop")
        await wait_for(pilot, lambda: ed.completing)
        assert [c.text for c in popup(ed)._items] == ["ID", "FULL_NAME"]
        await pilot.press("f")
        await wait_for(pilot, lambda: [c.text for c in popup(ed)._items] == ["FULL_NAME"])
        await pilot.press("tab")
        await pilot.pause()
        assert ed.text == "select p.FULL_NAME from people p"


async def test_escape_closes_without_changing_text(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac3"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac3")
        await type_text(pilot, "sel")
        await pilot.press("ctrl+space")
        await wait_for(pilot, lambda: ed.completing)
        await pilot.press("down")
        await pilot.press("escape")
        await pilot.pause()
        assert not ed.completing and ed.text == "sel"


async def test_no_popup_inside_string(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac4"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac4")
        await type_text(pilot, "select 'sel")
        await pilot.press("ctrl+space")
        await pilot.pause(0.3)
        assert not ed.completing


async def test_ddl_run_from_the_editor_refreshes_metadata_and_tree(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac5"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, ed = await setup(pilot, app, "ac5")
        await wait_for(
            pilot, lambda: any("PUBLIC" in str(n.label) for n in app.screen.schema.root.children)
        )
        ed.text = "create table fresh_one (a int)"
        await pilot.press("f5")
        await wait_for(pilot, lambda: not console.running)
        tables = [
            t.name
            for t in await console.meta.tables(
                next(n for n in await console.meta.namespaces() if n.name == "PUBLIC")
            )
        ]
        assert "FRESH_ONE" in tables


async def test_typing_a_word_opens_the_popup_by_itself(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac9"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac9")
        await type_text(pilot, "select * from pe")  # no Ctrl+Space
        await wait_for(pilot, lambda: ed.completing)
        assert popup(ed).current.text == "PEOPLE"


async def test_a_finished_word_does_not_hijack_enter(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac10"))))
    async with app.run_test(size=(140, 40)) as pilot:
        _, ed = await setup(pilot, app, "ac10")
        await type_text(pilot, "select * from PEOPLE")
        await pilot.pause(0.5)
        await pilot.press("enter")
        await pilot.pause()
        assert ed.text == "select * from PEOPLE\n"


async def test_schema_with_a_hyphen_completes_inside_an_open_quote(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac-hyphen"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, ed = await setup(pilot, app, "ac-hyphen")
        await console.session.execute('create schema "dbt-analytics"')
        await console.session.execute('create table "dbt-analytics".orders (id int)')
        console.meta.refresh()
        ed.text = 'select * from "dbt-an'
        ed.move_cursor((0, len(ed.text)))
        await pilot.press("ctrl+space")
        await wait_for(pilot, lambda: ed.completing)
        assert [c.text for c in popup(ed)._items] == ['"dbt-analytics"']
        await pilot.press("enter")
        await pilot.pause()
        assert ed.text == 'select * from "dbt-analytics"'  # one pair of quotes, not two


async def test_hyphen_schema_qualifier_lists_its_tables(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("ac-hyphen2"))))
    async with app.run_test(size=(140, 40)) as pilot:
        console, ed = await setup(pilot, app, "ac-hyphen2")
        await console.session.execute('create schema "dbt-analytics"')
        await console.session.execute('create table "dbt-analytics".orders (id int)')
        console.meta.refresh()
        ed.text = 'select * from "dbt-analytics".'
        ed.move_cursor((0, len(ed.text)))
        await pilot.press("ctrl+space")
        await wait_for(pilot, lambda: ed.completing)
        assert [c.text for c in popup(ed)._items] == ["ORDERS"]
