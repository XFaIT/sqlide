from sqlide.config.connections import Connection, ConnectionStore
from sqlide.db.metadata import Namespace, needs_choice, table_matches, visible_namespaces


def spaces(*names: str) -> list[Namespace]:
    return [Namespace(n) for n in names]


def names(items: list[Namespace]) -> list[str]:
    return [n.name for n in items]


def test_one_user_schema_shows_everything():
    shown, hidden = visible_namespaces(spaces("public", "information_schema"), "public", None)
    assert names(shown) == ["public", "information_schema"] and hidden == 0
    assert not needs_choice(spaces("public", "information_schema"))


def test_several_schemas_start_with_the_working_one_and_ask():
    many = spaces(*[f"s{i:03d}" for i in range(330)], "default")
    shown, hidden = visible_namespaces(many, "default", None)
    assert names(shown) == ["default"] and hidden == 330
    assert needs_choice(many)


def test_unknown_working_schema_shows_nothing_until_chosen():
    shown, hidden = visible_namespaces(spaces("a", "b", "c"), "", None)
    assert shown == [] and hidden == 3


def test_explicit_choice_wins_and_ignores_case():
    many = spaces("public", "Sales", "hr")
    shown, hidden = visible_namespaces(many, "public", ["sales", "HR"])
    assert names(shown) == ["Sales", "hr"] and hidden == 1


def test_choosing_nothing_shows_nothing():
    shown, hidden = visible_namespaces(spaces("a", "b"), "a", [])
    assert shown == [] and hidden == 2


def test_table_filter():
    assert table_matches("anything", "")
    assert table_matches("fact_sales", "fact_*")
    assert not table_matches("dim_date", "fact_*")
    assert table_matches("dim_date", "fact_*, date")  # plain word = substring
    assert table_matches("USERS", "users")


def test_connection_keeps_scope_in_the_file(tmp_path):
    store = ConnectionStore(tmp_path / "c.toml")
    store.save([Connection("db", "postgres", "jdbc:x", schemas=["a", "b"], table_filter="t_*")])
    got = store.load()[0]
    assert got.schemas == ["a", "b"] and got.table_filter == "t_*"


def test_never_chosen_is_not_written_and_empty_choice_is(tmp_path):
    store = ConnectionStore(tmp_path / "c.toml")
    store.save([Connection("a", "h2", "jdbc:x"), Connection("b", "h2", "jdbc:y", schemas=[])])
    text = (tmp_path / "c.toml").read_text()
    got = {c.name: c for c in store.load()}
    assert got["a"].schemas is None and got["b"].schemas == []
    assert text.count("schemas") == 1


def test_old_connection_files_without_scope_still_load(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[[connection]]\nname = "x"\ndriver = "h2"\nurl = "jdbc:h2:mem:x"\n')
    got = ConnectionStore(path).load()[0]
    assert got.schemas is None and got.table_filter == ""
