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
