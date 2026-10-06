from sqlide.history import HistoryStore


def store(tmp_path, limit=5000):
    return HistoryStore(tmp_path / "h.sqlite", limit)


def test_newest_first_and_fields(tmp_path):
    s = store(tmp_path)
    s.add("pg", "select 1", True, 5)
    s.add("pg", "select bad", False, 7, "syntax error")
    a, b = s.search()
    assert (a.sql, a.ok, a.error, a.elapsed_ms) == ("select bad", False, "syntax error", 7)
    assert (b.sql, b.ok, b.connection) == ("select 1", True, "pg")


def test_search_all_words_case_insensitive_and_literal_wildcards(tmp_path):
    s = store(tmp_path)
    s.add("a", "SELECT name FROM users", True, 1)
    s.add("a", "select 100% from t", True, 1)
    s.add("a", "select a_b from t", True, 1)
    assert [e.sql for e in s.search("users select")] == ["SELECT name FROM users"]
    assert [e.sql for e in s.search("100%")] == ["select 100% from t"]
    assert [e.sql for e in s.search("a_b")] == ["select a_b from t"]  # _ is not a wildcard
    assert s.search("zzz") == []


def test_filter_by_connection_and_success(tmp_path):
    s = store(tmp_path)
    s.add("a", "q1", True, 1)
    s.add("b", "q2", False, 1)
    assert [e.sql for e in s.search(connection="b")] == ["q2"]
    assert [e.sql for e in s.search(only_ok=True)] == ["q1"]


def test_limit_prunes_oldest_and_blank_is_ignored(tmp_path):
    s = store(tmp_path, limit=3)
    for i in range(6):
        s.add("a", f"q{i}", True, 1)
    s.add("a", "   ", True, 1)
    assert [e.sql for e in s.search()] == ["q5", "q4", "q3"]


def test_delete_clear_and_persistence(tmp_path):
    s = store(tmp_path)
    s.add("a", "keep", True, 1)
    s.add("a", "drop", True, 1)
    s.delete(s.search("drop")[0].id)
    s.close()
    again = store(tmp_path)
    assert [e.sql for e in again.search()] == ["keep"]
    again.clear()
    assert again.search() == []
