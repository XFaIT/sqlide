"""ResultGrid in isolation: a tiny host app, no database."""

import datetime as dt

import pytest
from textual.app import App, ComposeResult

from sqlide import clipboard
from sqlide.db.result import Column, DbError
from sqlide.ui.screens.grid_dialogs import CopyMenu, ValueViewer
from sqlide.ui.widgets.result_grid import ResultGrid
from sqlide.ui.widgets.result_view import ResultView
from tests.ui.helpers import wait_for

COLS = [Column("id", "INT", 4), Column("name", "VARCHAR", 12), Column("note", "VARCHAR", 12)]
ROWS = [(3, "bob", "x"), (1, "Alice", None), (2, "carol", "line1\nline2")]


class FakeSource:
    """Serves `pages` more pages of rows, then reports done."""

    def __init__(self, pages: int, fail: bool = False) -> None:
        self.pages, self.fail, self.calls, self.n = pages, fail, 0, 1000

    async def fetch_more(self, n):
        self.calls += 1
        if self.fail:
            raise DbError("cursor closed")
        self.pages -= 1
        rows = [(self.n + i, f"n{i}", None) for i in range(n)]
        self.n += n
        return rows, self.pages == 0

    async def close(self):
        pass


def make_app(rows=ROWS, source=None, page=5, height=12, width=60):
    class Host(App):
        def compose(self) -> ComposeResult:
            self.grid = ResultGrid(COLS, rows, source, page)
            yield ResultView(self.grid)

    return Host(), (width, height)


def line(grid, y):
    return "".join(s.text for s in grid.render_line(y))


async def test_renders_header_rows_nulls_and_gutter():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        g = app.grid
        assert "id" in line(g, 0) and "name" in line(g, 0) and "note" in line(g, 0)
        assert " 1 " in line(g, 1) and "bob" in line(g, 1)
        assert "<null>" in line(g, 2)
        assert "line1⏎line2" in line(g, 3)  # newline shown as a marker, not a row break


async def test_numbers_are_right_aligned():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        row = line(app.grid, 1)
        id_cell = row.split("│")[0][app.grid._gw :]
        assert id_cell.endswith("3") and id_cell.startswith(" ")


async def test_empty_result():
    app, size = make_app(rows=[])
    async with app.run_test(size=size) as pilot:
        await pilot.pause()
        assert "(no rows)" in line(app.grid, 1)
        await pilot.press("down", "ctrl+c")  # must not crash


async def test_navigation_and_selection_rect():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        app.grid.focus()
        await pilot.press("down", "right")
        assert app.grid.cursor == (1, 1)
        await pilot.press("shift+down", "shift+right")
        assert app.grid.selection_rect() == (1, 1, 2, 2)
        await pilot.press("up")  # plain move collapses the selection
        assert app.grid.selection_rect() == (1, 2, 1, 2)
        await pilot.press("ctrl+a")
        assert app.grid.selection_rect() == (0, 0, 2, 2)
        await pilot.press("ctrl+end")
        assert app.grid.cursor == (2, 2)
        await pilot.press("home")
        assert app.grid.cursor == (2, 0)
        await pilot.press("down", "down", "right", "right", "right", "right")
        assert app.grid.cursor == (2, 2)  # clamped at the edges


async def test_sort_by_key_and_header_indicator():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("s")
        assert [g.model.value(i, 0) for i in range(3)] == [1, 2, 3]
        assert "id ▲" in line(g, 0)
        await pilot.press("s")
        assert [g.model.value(i, 0) for i in range(3)] == [3, 2, 1] and "id ▼" in line(g, 0)
        await pilot.press("s")
        assert [g.model.value(i, 0) for i in range(3)] == [3, 1, 2] and "▲" not in line(g, 0)


async def test_multi_sort_shows_priorities():
    app, size = make_app(rows=[(1, "b", "z"), (2, "a", "y"), (3, "b", "x")])
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("right", "s", "right", "S")
        assert [g.model.value(i, 0) for i in range(3)] == [2, 3, 1]
        assert "name ▲1" in line(g, 0) and "note ▲2" in line(g, 0)


async def test_header_click_sorts_and_shift_click_adds():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        g = app.grid
        await pilot.pause()
        await pilot.click(ResultGrid, offset=(g._gw + 1, 0))
        await wait_for(pilot, lambda: g.model.sort == [(0, False)])
        await pilot.click(ResultGrid, offset=(g._gw + g._starts[1] + 1, 0), shift=True)
        await wait_for(pilot, lambda: g.model.sort == [(0, False), (1, False)])


async def test_mouse_click_and_drag_select():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        g = app.grid
        await pilot.mouse_down(ResultGrid, offset=(g._gw + 1, 1))
        await pilot.hover(ResultGrid, offset=(g._gw + g._starts[1] + 1, 3))
        await pilot.mouse_up(ResultGrid, offset=(g._gw + g._starts[1] + 1, 3))
        assert g.selection_rect() == (0, 0, 2, 1)


@pytest.fixture
def captured(monkeypatch):
    out = []
    monkeypatch.setattr(clipboard, "copy_native", lambda text: out.append(text) or "test")
    return out


async def test_ctrl_c_copies_selection_as_tsv(captured):
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        app.grid.focus()
        await pilot.press("shift+down", "shift+right", "ctrl+c")
        assert captured == ["3\tbob\n1\tAlice"]


async def test_copy_formats():
    app, size = make_app(rows=ROWS + [(4, "o'k", "a|b")])
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("ctrl+a")
        assert g.render_copy("tsv_header").splitlines()[0] == "id\tname\tnote"
        assert g.render_copy("csv").splitlines()[0] == "id,name,note"
        assert "a\\|b" in g.render_copy("markdown")
        assert '"name": "bob"' in g.render_copy("json")
        assert "'o''k'" in g.render_copy("insert")
        await pilot.press("ctrl+home")
        assert g.render_copy("cell") == "3"


async def test_copy_menu_flow(captured):
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        app.grid.focus()
        await pilot.press("ctrl+a", "y")
        await pilot.pause()
        assert isinstance(app.screen, CopyMenu)
        await pilot.press("down", "enter")  # "Values with header"
        await pilot.pause()
        assert captured and captured[0].startswith("id\tname\tnote")


async def test_filter_flow():
    app, size = make_app()
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("slash")
        view = app.query_one(ResultView)
        assert view.filter_input.display and view.filter_input.has_focus
        await pilot.press("c", "a", "r")
        assert len(g.model) == 1 and g.model.value(0, 1) == "carol"
        assert g.summary_text == "1 of 3 rows (filtered)"
        await pilot.press("enter")  # keep the filter, back to the table
        assert g.has_focus and len(g.model) == 1
        await pilot.press("slash", "escape")  # clears and hides it
        assert len(g.model) == 3 and not view.filter_input.display and g.has_focus


async def test_value_viewer_pretty_prints_json_and_closes():
    app, size = make_app(rows=[(1, "n", '{"a":1,"b":[1,2]}')])
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("right", "right", "enter")
        await pilot.pause()
        assert isinstance(app.screen, ValueViewer)
        assert '"a": 1' in app.screen._text and app.screen._is_json
        await pilot.press("escape")
        await pilot.pause()
        assert not isinstance(app.screen, ValueViewer)


async def test_load_more_manual_and_auto():
    src = FakeSource(pages=2)
    app, size = make_app(rows=[(i, "r", None) for i in range(5)], source=src, page=5)
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        assert g.summary_text == "5 rows (more…)"
        await pilot.press("l")
        await pilot.pause(0.2)
        assert g.model.total_rows == 10 and g.source is src
        await pilot.press("ctrl+end")  # near the end: fetches the last page automatically
        await pilot.pause(0.2)
        assert g.model.total_rows == 15 and g.source is None
        assert g.summary_text == "15 rows"


async def test_load_all():
    src = FakeSource(pages=4)
    app, size = make_app(rows=[(0, "r", None)], source=src, page=3)
    async with app.run_test(size=size) as pilot:
        app.grid.focus()
        await pilot.press("L")
        await pilot.pause(0.3)
        assert app.grid.model.total_rows == 13 and app.grid.source is None


async def test_load_more_error_is_reported_not_raised():
    src = FakeSource(pages=1, fail=True)
    app, size = make_app(rows=[(0, "r", None)], source=src)
    async with app.run_test(size=size) as pilot:
        app.grid.focus()
        await pilot.press("l")
        await pilot.pause(0.2)
        assert app.grid.source is None and app.grid.summary_text == "1 rows"
        assert any("cursor closed" in n.message for n in app._notifications)


async def test_horizontal_scroll_follows_cursor():
    wide = [Column(f"c{i}", "INT", 4) for i in range(12)]
    rows = [tuple(f"value-{r}-{c}-padding-padding" for c in range(12)) for r in range(3)]

    class Host(App):
        def compose(self) -> ComposeResult:
            self.grid = ResultGrid(wide, rows)
            yield self.grid

    app = Host()
    async with app.run_test(size=(50, 10)) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("end")
        await pilot.pause()
        assert g.scroll_offset.x > 0 and g.cursor == (0, 11)
        assert "value-0-11" in line(g, 1)
        await pilot.press("home")
        await pilot.pause()
        assert g.scroll_offset.x == 0


async def test_vertical_scroll_follows_cursor_and_sticky_header():
    rows = [(i, f"r{i}", None) for i in range(100)]
    app, size = make_app(rows=rows, height=10)
    async with app.run_test(size=size) as pilot:
        g = app.grid
        g.focus()
        await pilot.press("ctrl+end")
        await pilot.pause()
        assert "id" in line(g, 0)  # header stays on screen
        assert any("r99" in line(g, y) for y in range(1, 10))
        assert dt.date  # keep import used


async def test_alt3_focuses_the_visible_grid(make_ws):
    from sqlide.app import SqlideApp
    from sqlide.config.connections import Connection
    from tests.ui.helpers import connect_first, grids, wait_for

    app = SqlideApp(make_ws(Connection("h", "h2", "jdbc:h2:mem:focus3;DB_CLOSE_DELAY=-1")))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        c = app.screen.console
        c.editor.text = "select 1 as a"
        c.editor.focus()
        await pilot.press("f5")
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not c.running)
        await pilot.press("alt+3")
        await pilot.pause()
        assert app.focused is grids(app)[0]


async def test_f6_cycles_panes_and_alt_letters_focus(make_ws):
    from textual import events

    from sqlide.app import SqlideApp
    from sqlide.config.connections import Connection
    from tests.ui.helpers import connect_first

    app = SqlideApp(make_ws(Connection("h", "h2", "jdbc:h2:mem:cycle;DB_CLOSE_DELAY=-1")))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        main = app.screen
        main.sidebar.focus()
        await pilot.press("f6")
        assert app.focused is main.schema
        await pilot.press("f6")
        assert app.focused is main.console.editor
        await pilot.press("shift+f6")
        assert app.focused is main.schema
        app.post_message(events.Key("alt+q", "q"))  # what a real terminal sends
        await pilot.pause()
        assert app.focused is main.console.editor
        app.post_message(events.Key("alt+c", "c"))
        await pilot.pause()
        assert app.focused is main.sidebar
