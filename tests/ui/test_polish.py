"""Command palette entries, settings screen, driver manager."""

from textual.widgets import Input, OptionList, Switch

from sqlide.app import SqlideApp
from sqlide.config.settings import load_settings
from sqlide.drivers.registry import DriverRegistry
from sqlide.ui.screens.driver_manager import DriverEditor, DriverManager
from sqlide.ui.screens.settings import SettingsScreen
from tests.conftest import CACHE
from tests.ui.helpers import wait_for


async def test_palette_lists_our_commands_and_they_run(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cmds = {c.title: c for c in app.get_system_commands(app.screen)}
        assert {"Run statement", "Query history", "Drivers", "Settings", "Format SQL"} <= set(cmds)
        ed = app.main.console.editor
        ed.text = "select a,b from t"
        ed.focus()
        cmds["Format SQL"].callback()
        await pilot.pause()
        assert ed.text.startswith("SELECT\n  a,")
        cmds["Settings"].callback()
        await wait_for(pilot, lambda: isinstance(app.screen, SettingsScreen))


async def test_settings_save_applies_and_persists(make_ws, tmp_path, monkeypatch):
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "cfg"))
    ws = make_ws()
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.main.action_settings()
        await wait_for(pilot, lambda: isinstance(app.screen, SettingsScreen))
        app.screen.query_one("#fetch", Input).value = "250"
        app.screen.query_one("#blank", Switch).value = False
        await pilot.click("#save")
        await wait_for(pilot, lambda: not isinstance(app.screen, SettingsScreen))
        assert ws.settings.fetch_size == 250 and ws.settings.split_on_blank_line is False
        assert app.main.console.editor.blank_line is False
        assert load_settings().fetch_size == 250


async def test_settings_rejects_bad_numbers(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.main.action_settings()
        await wait_for(pilot, lambda: isinstance(app.screen, SettingsScreen))
        app.screen.query_one("#fetch", Input).value = "0"
        await pilot.click("#save")
        await pilot.pause()
        assert isinstance(app.screen, SettingsScreen)
        assert "Rows per page" in str(app.screen.query_one("#settings-error").render())


async def test_driver_manager_shows_state_and_adds_custom_jar(make_ws, h2, tmp_path):
    jar = str(DriverRegistry(CACHE / "drivers", CACHE / "drivers.toml").jar_paths("h2")[0])
    ws = make_ws(registry=DriverRegistry(tmp_path / "drv", tmp_path / "drivers.toml"))
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.main.action_drivers()
        await wait_for(pilot, lambda: isinstance(app.screen, DriverManager))
        lst = app.screen.query_one("#driver-list", OptionList)
        names = [str(lst.get_option_at_index(i).prompt) for i in range(lst.option_count)]
        assert any("PostgreSQL" in n and "not installed" in n for n in names)
        await pilot.press("a")
        await wait_for(pilot, lambda: isinstance(app.screen, DriverEditor))
        app.screen.query_one("#id", Input).value = "my-h2"
        app.screen.query_one("#source", Input).value = jar
        await pilot.click("#ok")
        await wait_for(pilot, lambda: isinstance(app.screen, DriverManager))
        d = ws.registry.get("my-h2")
        assert d.class_name == "org.h2.Driver" and d.jars == [jar]
        names = [str(lst.get_option_at_index(i).prompt) for i in range(lst.option_count)]
        assert any("custom jars" in n for n in names)


async def test_driver_editor_reports_errors(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 50)) as pilot:
        await pilot.pause()
        app.main.action_drivers()
        await wait_for(pilot, lambda: isinstance(app.screen, DriverManager))
        await pilot.press("a")
        await wait_for(pilot, lambda: isinstance(app.screen, DriverEditor))
        await pilot.click("#ok")
        await pilot.pause()
        assert isinstance(app.screen, DriverEditor)
        assert "Id" in str(app.screen.query_one("#driver-error").render())
