from pathlib import Path

from sqlide.consoles import CONSOLE, FILE, ConsoleStore, TabState, safe_dirname, write_text_atomic


def store(tmp_path):
    return ConsoleStore(tmp_path / "consoles", tmp_path / "state.toml")


def test_new_console_files_are_numbered_per_connection(tmp_path):
    s = store(tmp_path)
    a = s.new_console_file("pg-prod")
    b = s.new_console_file("pg-prod")
    c = s.new_console_file("other")
    d = s.new_console_file(None)
    assert [p.name for p in (a, b, c)] == ["console_1.sql", "console_2.sql", "console_1.sql"]
    assert a.parent.name == "pg-prod" and d.parent.name == "no-connection"
    assert all(p.exists() for p in (a, b, c, d))


def test_dirname_is_filesystem_safe():
    assert safe_dirname("a/b:c d") == "a_b_c_d"
    assert safe_dirname("../..") == "_"
    assert safe_dirname("") == "_"


def test_crlf_files_keep_their_line_endings(tmp_path):
    p = tmp_path / "x" / "q.sql"
    write_text_atomic(p, "select 'é';\r\nselect 2\r\n")
    text, newline = ConsoleStore.read(p)
    assert text == "select 'é';\nselect 2\n" and newline == "\r\n"
    ConsoleStore.write(p, text + "select 3", newline)
    assert p.read_bytes() == "select 'é';\r\nselect 2\r\nselect 3".encode()
    assert [f.name for f in p.parent.iterdir()] == ["q.sql"]  # no temp file left


def test_lf_files_stay_lf_and_lone_cr_is_normalised(tmp_path):
    p = tmp_path / "q.sql"
    write_text_atomic(p, "a\nb\n")
    assert ConsoleStore.read(p) == ("a\nb\n", "\n")
    write_text_atomic(p, "a\rb")
    assert ConsoleStore.read(p) == ("a\nb", "\n")


def test_state_roundtrip(tmp_path):
    s = store(tmp_path)
    tabs = [TabState(CONSOLE, "/a/console_1.sql", "pg", True), TabState(FILE, "/b/q.sql")]
    s.save_state(tabs)
    assert s.load_state() == tabs


def test_missing_or_damaged_state_is_empty(tmp_path):
    s = store(tmp_path)
    assert s.load_state() == []
    s.state_file.write_text("this is = = not toml")
    assert s.load_state() == []


def test_unknown_entries_are_skipped(tmp_path):
    s = store(tmp_path)
    s.state_file.write_text(
        '[[tab]]\nkind="console"\npath="/p"\n[[tab]]\nkind="weird"\npath="/q"\n[[tab]]\nbogus=1\n'
    )
    assert [t.path for t in s.load_state()] == ["/p"]
    assert isinstance(Path(s.load_state()[0].path), Path)
