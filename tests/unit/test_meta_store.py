import json

from sqlide.db.meta_store import MetaStore
from sqlide.db.metadata import Column, MetaCache, Namespace, Table


def cache_with(disk):
    return MetaCache(None, disk)  # type: ignore[arg-type]  # no session needed for restore/save


def test_snapshot_round_trip(tmp_path):
    disk = MetaStore(tmp_path).for_connection("db/1", "jdbc:x")
    a = cache_with(disk)
    ns = Namespace("app")
    a._catalogs = []
    a._namespaces = [ns]
    a._tables = {ns.key: [Table("app", "users", "TABLE")]}
    a._columns = {("", "app", "users"): [Column("id", "INT", False, True)]}
    a.flush()
    b = cache_with(disk)
    assert b._namespaces == [ns] and b._catalogs == []
    assert b._tables[ns.key][0].name == "users"
    assert b._columns[("", "app", "users")] == [Column("id", "INT", False, True)]
    assert b.cached_at is not None


def test_three_level_namespaces_are_derived_not_stored(tmp_path):
    disk = MetaStore(tmp_path).for_connection("dbx", "jdbc:databricks:x")
    a = cache_with(disk)
    a._catalogs = ["main", "hive"]
    a._catalog_schemas = {"main": [Namespace("dbt-analytics", False, "main")]}
    a.flush()
    b = cache_with(disk)
    assert b._catalogs == ["main", "hive"] and b._namespaces is None
    assert b._catalog_schemas["main"][0].key == "main/dbt-analytics"


def test_refresh_drops_the_file(tmp_path):
    disk = MetaStore(tmp_path).for_connection("c", "u")
    a = cache_with(disk)
    a._catalogs = []
    a.flush()
    assert disk.path.exists()
    a.refresh()
    assert not disk.path.exists() and a.cached_at is None


def test_other_url_or_name_gets_its_own_file(tmp_path):
    store = MetaStore(tmp_path)
    assert store.for_connection("c", "u1").path != store.for_connection("c", "u2").path
    assert store.for_connection("c1", "u").path != store.for_connection("c2", "u").path


def test_garbage_and_foreign_files_are_ignored(tmp_path):
    disk = MetaStore(tmp_path).for_connection("c", "u")
    disk.path.parent.mkdir(parents=True, exist_ok=True)
    disk.path.write_text("{not json")
    assert cache_with(disk)._tables == {}
    disk.path.write_text(json.dumps({"version": 99}))
    assert cache_with(disk)._tables == {}
    disk.path.write_text(json.dumps({"version": 1, "ts": 1}))  # missing keys
    assert cache_with(disk)._tables == {}
