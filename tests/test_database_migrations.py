import sqlite3

from daylens.repositories.connection_repository import init_db
from daylens.repositories.settings_repository import merge_custom_rules


def test_init_db_records_schema_version(tmp_path):
    db = tmp_path / "migration.db"
    conn = init_db(str(db))
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    assert version == "3"
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
    assert version == "3"
    migrated.close()


def test_v2_empty_legacy_title_rules_migrate_to_inherit_mode(tmp_path):
    db = tmp_path / "migration.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '2');
        CREATE TABLE custom_rules (
            category_key TEXT PRIMARY KEY,
            display_name TEXT,
            active_rule TEXT,
            process_names TEXT,
            title_keywords TEXT,
            title_patterns TEXT DEFAULT ''
        );
        INSERT INTO custom_rules VALUES(
            'reading', '阅读学习', 'interactive_required',
            'zotero.exe', '用户关键词', ''
        );
        """
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db))
    row = migrated.execute(
        "SELECT title_keywords_mode, title_patterns_mode "
        "FROM custom_rules WHERE category_key='reading'"
    ).fetchone()

    assert row == ("replace", "inherit")
    assert migrated.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0] == "3"
    migrated.close()

    config = {
        "categories": {
            "reading": {
                "display_name": "阅读学习",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["zotero.exe"],
                    "title_keywords": ["工厂关键词"],
                    "title_patterns": [r"第\d+章"],
                },
            }
        }
    }
    merge_custom_rules(config, str(db))
    reading_match = config["categories"]["reading"]["match"]
    assert reading_match["title_keywords"] == ["用户关键词"]
    assert reading_match["title_patterns"] == [r"第\d+章"]


def test_v2_legacy_process_list_remains_an_explicit_replacement(tmp_path):
    db = tmp_path / "migration.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '2');
        CREATE TABLE custom_rules (
            category_key TEXT PRIMARY KEY,
            display_name TEXT,
            active_rule TEXT,
            process_names TEXT,
            title_keywords TEXT,
            title_patterns TEXT DEFAULT ''
        );
        INSERT INTO custom_rules VALUES(
            'office', '办公套件', 'interactive_required',
            'excel.exe', '', ''
        );
        """
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db))
    mode = migrated.execute(
        "SELECT process_names_mode FROM custom_rules "
        "WHERE category_key='office'"
    ).fetchone()[0]
    migrated.close()
    config = {
        "categories": {
            "office": {
                "display_name": "办公套件",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["excel.exe", "winword.exe"],
                    "title_keywords": [],
                    "title_patterns": [],
                },
            }
        }
    }

    merge_custom_rules(config, str(db))

    assert mode == "replace"
    assert config["categories"]["office"]["match"]["process_names"] == [
        "excel.exe"
    ]
