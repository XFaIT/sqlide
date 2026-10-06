"""Console tabs: create, autosave, restore, files, lazy connect, transactions."""

from pathlib import Path

from textual.widgets import Input

from sqlide.app import SqlideApp
from sqlide.config.connections import Connection
from sqlide.ui.screens.dialogs import ConfirmScreen, PathPrompt
from sqlide.ui.screens.main import MainScreen
from tests.ui.helpers import connect_first, grids, wait_for

URL = "jdbc:h2:mem:{};DB_CLOSE_DELAY=-1"


def tabs(app):
    return app.screen.tabs


def consoles(app):
    return tabs(app).consoles()


def active(app):
    return tabs(app).active_console


async def test_starts_with_one_console_backed_by_a_file(make_ws):
    ws = make_ws()
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        [c] = consoles(app)
        assert c.kind == "console" and c.path.name == "console_1.sql" and c.path.exists()
        assert c.title == "console_1"


async def test_new_tab_has_its_own_text_and_file(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        first = active(app)
        first.editor.text = "select 'first'"
        await pilot.press("ctrl+t")
        await wait_for(pilot, lambda: len(consoles(app)) == 2)
        second = active(app)
        assert second is not first and second.editor.text == "" and second.path != first.path
        assert first.editor.text == "select 'first'"
        await pilot.press("alt+left")
        await pilot.pause()
        assert active(app) is first
        await pilot.press("alt+right")
        await pilot.pause()
        assert active(app) is second


async def test_autosave_writes_after_a_pause(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        c = active(app)
        c.editor.text = "select 42"
        assert c.path.read_text() == ""  # debounced, not yet
        await pilot.pause(1.3)
        assert c.path.read_text() == "select 42"


async def test_tabs_and_text_survive_restart(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("tab1")))
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        active(app).editor.text = "select 1"
        await pilot.press("ctrl+t")
        await wait_for(pilot, lambda: len(consoles(app)) == 2)
        active(app).editor.text = "select 2"
        await pilot.press("alt+left")  # leave the first tab active
        await pilot.pause()
        await pilot.press("ctrl+q")
        await pilot.pause()

    app2 = SqlideApp(ws)
    async with app2.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        cs = consoles(app2)
        assert [c.editor.text for c in cs] == ["select 1", "select 2"]
        assert [c.conn_name for c in cs] == ["h", "h"]  # intended connection remembered
        assert active(app2) is cs[0]
        assert all(c.session is None for c in cs)  # but nothing connects by itself


async def test_lazy_connect_on_first_run(make_ws):
    ws = make_ws(Connection("h", "h2", URL.format("tab2")))
    app = SqlideApp(ws)
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        active(app).editor.text = "select 7 as seven"
        await pilot.press("ctrl+q")
        await pilot.pause()

    app2 = SqlideApp(ws)
    async with app2.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        c = active(app2)
        c.editor.focus()
        await pilot.press("f5")  # no session yet: connects, then runs
        await wait_for(pilot, lambda: len(grids(app2)) == 1 and not c.running)
        assert c.session is not None and grids(app2)[0].model.row(0) == (7,)


async def test_each_tab_gets_its_own_session(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("tab3"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        first = active(app)
        await pilot.press("ctrl+t")
        await wait_for(pilot, lambda: len(consoles(app)) == 2)
        second = active(app)
        second.editor.text = "select 1"
        second.editor.focus()
        await pilot.press("f5")
        await wait_for(pilot, lambda: second.session is not None and not second.running)
        assert first.session is not second.session and first.session.connected


async def test_open_edit_save_file_keeps_crlf(make_ws, tmp_path):
    f = tmp_path / "q.sql"
    f.write_bytes(b"select 1;\r\nselect 2;\r\n")
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("ctrl+o")
        await wait_for(pilot, lambda: isinstance(app.screen, PathPrompt))
        app.screen.query_one("#path", Input).value = str(f)
        await pilot.press("enter")
        await wait_for(pilot, lambda: len(consoles(app)) == 2)
        c = active(app)
        assert c.kind == "file" and c.title == "q.sql" and c.editor.text == "select 1;\nselect 2;\n"
        c.editor.text += "select 3;\n"
        await pilot.pause()
        assert c.dirty and c.title.startswith("● ")
        c.editor.focus()
        await pilot.press("ctrl+s")
        await pilot.pause(0.2)
        assert f.read_bytes() == b"select 1;\r\nselect 2;\r\nselect 3;\r\n"
        assert not c.dirty and c.title == "q.sql"


async def test_opening_an_open_file_just_activates_it(make_ws, tmp_path):
    f = tmp_path / "q.sql"
    f.write_text("select 1")
    app = SqlideApp(make_ws(), files=[f])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert active(app).path == f and len(consoles(app)) == 1  # restored tab list was empty
        await pilot.press("ctrl+t")
        await wait_for(pilot, lambda: len(consoles(app)) == 2)
        await app.screen.open_path(f)
        await pilot.pause()
        assert len(consoles(app)) == 2 and active(app).path == f


async def test_cli_files_are_opened_and_new_paths_are_created_on_save(make_ws, tmp_path):
    existing = tmp_path / "a.sql"
    existing.write_text("select 1")
    brand_new = tmp_path / "sub" / "new.sql"
    app = SqlideApp(make_ws(), files=[existing, brand_new])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert {c.path.name for c in consoles(app)} == {"a.sql", "new.sql"}
        c = active(app)
        assert c.path == brand_new and c.editor.text == ""
        c.editor.text = "select 'x'"
        c.editor.focus()
        await pilot.press("ctrl+s")
        await pilot.pause(0.2)
        assert brand_new.read_text() == "select 'x'"


async def test_save_console_as_turns_it_into_a_file(make_ws, tmp_path):
    out = tmp_path / "saved.sql"
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        c = active(app)
        c.editor.text = "select 5"
        c.editor.focus()
        await pilot.press("ctrl+s")
        await wait_for(pilot, lambda: isinstance(app.screen, PathPrompt))
        app.screen.query_one("#path", Input).value = str(out)
        await pilot.press("enter")
        await wait_for(pilot, lambda: out.exists())
        assert out.read_text() == "select 5" and c.kind == "file" and c.title == "saved.sql"


async def test_close_tab_confirms_when_dirty_and_never_leaves_zero_tabs(make_ws, tmp_path):
    f = tmp_path / "q.sql"
    f.write_text("select 1")
    app = SqlideApp(make_ws(), files=[f])
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        c = active(app)
        c.editor.text = "select changed"
        await pilot.pause()
        await pilot.press("ctrl+f4")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("n")  # keep it
        await wait_for(pilot, lambda: isinstance(app.screen, MainScreen))
        assert len(consoles(app)) == 1 and active(app) is c
        await pilot.press("ctrl+f4")
        await wait_for(pilot, lambda: isinstance(app.screen, ConfirmScreen))
        await pilot.press("y")
        await wait_for(pilot, lambda: active(app) is not c)
        [fresh] = consoles(app)  # closing the last tab opens a fresh console
        assert fresh.kind == "console" and f.read_text() == "select 1"  # file untouched


async def test_manual_transaction_status_commit_and_rollback(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("tab4"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        c = active(app)
        assert c.status.tx == "Auto"
        c.editor.focus()
        c.editor.text = "create table t(a int)"
        await pilot.press("f5")
        await wait_for(pilot, lambda: not c.running and c.status.message.endswith("ms"))
        await pilot.press("f8")
        await wait_for(pilot, lambda: c.status.tx == "Manual")
        c.editor.text = "insert into t values (1)"
        await pilot.press("f5")
        await wait_for(pilot, lambda: not c.running and c.status.tx == "Manual*")
        await pilot.press("f10")
        await wait_for(pilot, lambda: c.status.tx == "Manual")
        c.editor.text = "select count(*) from t"
        await pilot.press("f5")
        await wait_for(pilot, lambda: len(grids(app)) == 1 and not c.running)
        assert grids(app)[0].model.row(0) == (0,)  # rolled back
        c.editor.text = "insert into t values (2)"
        await pilot.press("f5")
        await wait_for(pilot, lambda: not c.running and c.status.tx == "Manual*")
        await pilot.press("f9")
        await wait_for(pilot, lambda: c.status.tx == "Manual")
        await pilot.press("f8")
        await wait_for(pilot, lambda: c.status.tx == "Auto")
        c.editor.text = "select count(*) from t"
        await pilot.press("f5")
        await wait_for(pilot, lambda: not c.running and grids(app)[0].model.row(0) == (1,))


def test_state_path_helper_is_isolated(tmp_path):
    from sqlide.config import paths

    assert Path(paths.data_dir()) == tmp_path / "_data"  # the autouse fixture is in effect


async def test_tab_label_shows_connection_name(make_ws):
    app = SqlideApp(make_ws(Connection("h2-local", "h2", URL.format("tablabel"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        pane = active(app).parent
        label = tabs(app).get_tab(pane.id).label.plain
        assert label == "console_1 [h2-local]"


async def test_format_and_comment_actions(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        ed = active(app).editor
        ed.text = "select a,b from t where x=1;\n\nselect 2"
        ed.focus()
        ed.move_cursor((0, 3))
        await pilot.press("f7")
        await pilot.pause()
        assert ed.text == "SELECT\n  a,\n  b\nFROM t\nWHERE\n  x = 1;\n\nselect 2"
        ed.move_cursor((0, 0))
        await pilot.press("alt+slash")
        await pilot.pause()
        assert ed.text.startswith("-- SELECT\n  a,")
        await pilot.press("alt+slash")
        await pilot.pause()
        assert ed.text.startswith("SELECT\n  a,")
        ed.text = "select from where"
        ed.move_cursor((0, 2))
        await pilot.press("f7")  # unparsable: text untouched
        await pilot.pause()
        assert ed.text == "select from where"


async def test_keymap_file_rebinds_run(make_ws, tmp_path, monkeypatch):
    monkeypatch.setenv("SQLIDE_CONFIG_DIR", str(tmp_path / "cfg"))
    (tmp_path / "cfg").mkdir()
    (tmp_path / "cfg" / "keymap.toml").write_text('[keys]\n"editor.run" = "f4"\n')
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("keymap"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        c = active(app)
        c.editor.text = "select 5"
        c.editor.focus()
        await pilot.press("f5")  # no longer bound
        await pilot.pause(0.3)
        assert grids(app) == []
        await pilot.press("f4")
        await wait_for(pilot, lambda: len(grids(app)) == 1)


async def test_enter_connects_without_moving_the_cursor_first(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("firstenter"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert app.screen.sidebar.index == 0
        app.screen.sidebar.focus()
        await pilot.press("enter")
        await wait_for(pilot, lambda: active(app).session is not None)


async def test_frame_is_not_drawn_below_the_text(make_ws):
    app = SqlideApp(make_ws())
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        ed = active(app).editor
        ed.text = "select 1"
        ed.move_cursor((0, 3))
        await pilot.pause()
        assert ed.frame_lines == (0, 0)
        assert "▏" in ed.render_line(0).text[:6]
        for row in (1, 5, 20):
            assert "▏" not in ed.render_line(row).text[:6]


async def test_schema_reads_use_their_own_connection_and_do_not_wait_for_a_query(make_ws, tmp_path):
    import asyncio

    url = f"jdbc:h2:file:{tmp_path / 'meta'}"
    app = SqlideApp(make_ws(Connection("h", "h2", url)))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        c = active(app)
        await wait_for(pilot, lambda: c.meta_session is not None)
        assert c.meta_session is not c.session
        c.editor.text = "select sum(x * x % 7) from system_range(1, 3000000000)"
        c.editor.focus()
        await pilot.press("f5")
        await wait_for(pilot, lambda: c.running)
        spaces = await asyncio.wait_for(c.meta.namespaces(), 10)  # would block on one connection
        assert any(n.name == "PUBLIC" for n in spaces)
        c.action_cancel()
        await wait_for(pilot, lambda: not c.running)


async def test_in_memory_database_keeps_the_shared_session(make_ws):
    app = SqlideApp(make_ws(Connection("h", "h2", URL.format("sharedmeta"))))
    async with app.run_test(size=(120, 40)) as pilot:
        await connect_first(pilot, app)
        await pilot.pause(0.5)
        assert active(app).meta_session is None
