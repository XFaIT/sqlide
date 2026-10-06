import pytest

from sqlide.db.factory import is_private_database


@pytest.mark.parametrize(
    ("url", "private"),
    [
        ("jdbc:h2:mem:demo;DB_CLOSE_DELAY=-1", True),
        ("jdbc:sqlite::memory:", True),
        ("jdbc:duckdb:", True),
        ("jdbc:duckdb::memory:", True),
        ("jdbc:duckdb:/tmp/x.db", False),
        ("jdbc:h2:file:/tmp/x", False),
        ("jdbc:postgresql://localhost:5432/db", False),
        ("jdbc:sqlite:/tmp/x.db", False),
        ("jdbc:derby:memory:db;create=true", True),
    ],
)
def test_is_private_database(url, private):
    assert is_private_database(url) is private
