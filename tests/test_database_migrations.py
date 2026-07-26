import sqlite3

from daylens.repositories.connection_repository import init_db


def test_init_db_records_schema_version(tmp_path):
    db = tmp_path / "migration.db"
    conn = init_db(str(db))
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    assert version == "2"
    conn.close()


def test_v1_custom_rules_migration_adds_title_patterns_without_losing_rows(tmp_path):
    db = tmp_path / "migration.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '1');
        CREATE TABLE custom_rules (
            category_key TEXT PRIMARY KEY,
            display_name TEXT,
            active_rule TEXT,
            process_names TEXT,
            title_keywords TEXT
        );
        INSERT INTO custom_rules VALUES(
            'reading', '阅读学习', 'interactive_required',
            'zotero.exe', '用户关键词'
        );
        """
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db))

    columns = {
        row[1] for row in migrated.execute("PRAGMA table_info(custom_rules)").fetchall()
    }
    row = migrated.execute(
        "SELECT display_name, process_names, title_keywords, title_patterns "
        "FROM custom_rules WHERE category_key='reading'"
    ).fetchone()
    version = migrated.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0]
    assert "title_patterns" in columns
    assert row == ("阅读学习", "zotero.exe", "用户关键词", "")
    assert version == "2"
    migrated.close()
