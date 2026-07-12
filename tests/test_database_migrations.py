import sqlite3

from daylens.repositories.connection_repository import init_db


def test_init_db_records_schema_version(tmp_path):
    db = tmp_path / "migration.db"
    conn = init_db(str(db))
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    assert version == "1"
    conn.close()
