import pytest

from sqlide.config.keymap import is_modifier_only, load_keymap, save_override


@pytest.mark.parametrize(
    "key",
    ["ctrl", "left_control", "right_shift", "left_alt", "left_super", "iso_level3_shift",
     "caps_lock", "ctrl+left_control"],
)  # fmt: skip
def test_bare_modifiers_are_not_bindable(key):
    assert is_modifier_only(key)


@pytest.mark.parametrize("key", ["f5", "ctrl+j", "ctrl+shift+f5", "alt+e", "left", "ctrl+left"])
def test_real_keys_are_bindable(key):
    assert not is_modifier_only(key)


def test_saved_bare_modifier_is_dropped_on_load(tmp_path):
    path = tmp_path / "keymap.toml"
    save_override("editor.run", "left_control", path)
    save_override("main.history", "ctrl+h", path)
    assert load_keymap(path) == {"main.history": "ctrl+h"}
