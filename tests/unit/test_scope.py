from sqlide.config.connections import Connection, ConnectionStore
from sqlide.db.metadata import Namespace, table_matches, visible_namespaces


def spaces(*names: str) -> list[Namespace]:
    return [Namespace(n) for n in names]


def names(items: list[Namespace]) -> list[str]:
    return [n.name for n in items]


def test_small_database_shows_everything_by_default():
    shown, hidden = visible_namespaces(spaces("public", "app", "information_schema"), "public", [])
    assert names(shown) == ["public", "app", "information_schema"] and hidden == 0


def test_big_database_shows_only_the_working_schema():
    many = spaces(*[f"s{i:03d}" for i in range(330)], "default")
    shown, hidden = visible_namespaces(many, "default", [])
    assert names(shown) == ["default"] and hidden == 330


def test_big_database_without_a_known_working_schema_shows_a_page():
    many = spaces(*[f"s{i:03d}" for i in range(50)])
    shown, hidden = visible_namespaces(many, "", [])
    assert len(shown) == 20 and hidden == 30


def test_explicit_choice_wins_and_ignores_case():
    many = spaces("public", "Sales", "hr")
    shown, hidden = visible_namespaces(many, "public", ["sales", "HR"])
    assert names(shown) == ["Sales", "hr"] and hidden == 1


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


def test_old_connection_files_without_scope_still_load(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[[connection]]\nname = "x"\ndriver = "h2"\nurl = "jdbc:h2:mem:x"\n')
    got = ConnectionStore(path).load()[0]
    assert got.schemas == [] and got.table_filter == ""
