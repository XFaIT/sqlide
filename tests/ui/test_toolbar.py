"""Icon toolbar: tooltips carry the live key, clicks run actions, idle buttons are dim."""

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from sqlide.ui.widgets.toolbar import IconButton
from tests.ui.helpers import connect_first, console, grids, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


def button(app, title):
    return next(b for b in app.screen.query(IconButton) if b.tool.title == title)


async def test_tooltip_names_the_button_its_key_and_what_it_does(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        tip = str(button(app, "Run").tooltip)
        assert tip.startswith("Run (Ctrl+J / F5 / Ctrl+Enter)")
        assert "statement under the cursor" in tip


async def test_tooltip_follows_a_rebound_key(make_ws, tmp_path, monkeypatch):
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "cfg"))
    from sqlide.config.keymap import save_override

    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        save_override("editor.run", "f4")
        app.set_keymap({"editor.run": "f4"})
        app.main.toolbar.refresh_tips()
        assert str(button(app, "Run").tooltip).startswith("Run (F4)")


async def test_clicking_run_executes_the_statement(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("toolbarrun"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        c = console(app)
        c.editor.text = "select 1 as a"
        await pilot.click(IconButton, offset=(1, 0))  # first button: Run
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not c.running)


async def test_cancel_and_commit_are_dim_while_idle(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("toolbardim"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        await pilot.pause(0.6)
        assert button(app, "Cancel").has_class("-off")
        assert button(app, "Commit").has_class("-off")  # auto-commit mode
        assert not button(app, "Run").has_class("-off")
