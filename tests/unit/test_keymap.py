from sqlide.config.keymap import load_keymap
from sqlide.ui.keymap import catalogue


def test_missing_file_gives_empty(tmp_path):
    assert load_keymap(tmp_path / "none.toml") == {}


def test_reads_keys_and_ignores_junk(tmp_path):
    f = tmp_path / "k.toml"
    f.write_text('[keys]\n"editor.run" = "f6"\n"x" = 3\n"y" = "  "\n')
    assert load_keymap(f) == {"editor.run": "f6"}


def test_malformed_file_is_ignored(tmp_path):
    f = tmp_path / "k.toml"
    f.write_text("[keys\n")
    assert load_keymap(f) == {}


def test_catalogue_ids_are_unique_and_dotted():
    ids = [i.id for i in catalogue()]
    assert len(ids) == len(set(ids)) and all("." in i for i in ids)


def test_format_keys_reads_like_a_human_wrote_it():
    from sqlide.ui.keymap import format_keys

    assert format_keys("ctrl+j,f5,ctrl+enter") == "Ctrl+J / F5 / Ctrl+Enter"
    assert format_keys("ctrl+j,f5", limit=1) == "Ctrl+J"
    assert format_keys("shift+f5") == "Shift+F5"
    assert format_keys("ctrl+pagedown") == "Ctrl+PgDn"
    assert format_keys("ctrl+slash") == "Ctrl+/"


def test_catalogue_applies_overrides_and_marks_them():
    infos = {i.id: i for i in catalogue({"editor.run": "f4"})}
    assert infos["editor.run"].keys == "f4" and infos["editor.run"].overridden
    assert not infos["editor.run_all"].overridden


def test_default_run_key_is_ctrl_first():
    assert {i.id: i for i in catalogue({})}["editor.run"].keys.startswith("ctrl+j")


def test_save_override_keeps_other_entries_and_can_reset(tmp_path):
    from sqlide.config.keymap import save_override

    f = tmp_path / "k.toml"
    save_override("editor.run", "f4", f)
    save_override("main.history", "ctrl+h", f)
    assert load_keymap(f) == {"editor.run": "f4", "main.history": "ctrl+h"}
    save_override("editor.run", None, f)
    assert load_keymap(f) == {"main.history": "ctrl+h"}
