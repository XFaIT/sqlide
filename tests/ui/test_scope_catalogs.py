"""Scope dialog with several databases: databases left, schemas of the highlighted one right."""

from textual.app import App
from textual.widgets import SelectionList

from sqlide.db.metadata import Namespace
from sqlide.ui.screens.scope import ScopeChoice, ScopeScreen
from tests.ui.helpers import wait_for


def listed(screen):
    found = screen.query("#scope-list")
    return len(found.first(SelectionList).options) if found else -1


async def test_two_pane_dialog_lists_schemas_per_database_and_returns_both():
    async def loader(catalog):
        return [Namespace(n, catalog=catalog) for n in ("dbo", "sales")]

    result: list[ScopeChoice | None] = []
    app = App()
    async with app.run_test(size=(120, 40)) as pilot:
        screen = ScopeScreen(
            [],
            [],
            "",
            catalogs=["master", "shop"],
            chosen_catalogs=["master"],
            loader=loader,
            start_catalog="master",
        )
        app.push_screen(screen, result.append)
        await wait_for(pilot, lambda: listed(screen) == 2)
        screen.query_one("#scope-list", SelectionList).select("master/sales")
        cats = screen.query_one("#scope-cats", SelectionList)
        cats.highlighted = 1
        await wait_for(pilot, lambda: screen._current_cat == "shop")
        screen.query_one("#scope-list", SelectionList).select("shop/dbo")
        await pilot.pause()
        screen.action_save()
        await pilot.pause()
    assert result[0] is not None
    assert result[0].schemas == ["master/sales", "shop/dbo"]
    assert result[0].catalogs == ["master"]


async def test_f1_opens_help_listing_keys(make_ws):
    from sqlide.app import SqlideApp
    from sqlide.ui.screens.help import HelpScreen

    app = SqlideApp(make_ws())
    async with app.run_test(size=(140, 40)) as pilot:
        await pilot.press("f1")
        await wait_for(pilot, lambda: isinstance(app.screen, HelpScreen))
        await pilot.pause()
        assert app.screen.query_one("#help-list").option_count > 10
        await pilot.press("escape")
        await wait_for(pilot, lambda: not isinstance(app.screen, HelpScreen))
