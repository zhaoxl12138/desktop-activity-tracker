import sqlite3

import pytest

from daylens.repositories import connection_repository
from daylens.repositories.connection_repository import init_db
from daylens.repositories.settings_repository import merge_custom_rules


def test_init_db_records_schema_version(tmp_path):
    db = tmp_path / "migration.db"
    conn = init_db(str(db))
    version = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0]
    columns = {
        row[1]: (row[2], row[4])
        for row in conn.execute("PRAGMA table_info(activity_sessions)").fetchall()
    }
    assert version == "4"
    assert columns["engaged_seconds"] == ("INTEGER", "0")
    assert columns["passive_seconds"] == ("INTEGER", "0")
    assert columns["metric_version"] == ("TEXT", "'legacy'")
    assert columns["classification_version"] == ("TEXT", "'legacy'")
    indexes = {
        row[1]
        for row in conn.execute("PRAGMA index_list(activity_sessions)")
    }
    assert "idx_sessions_engaged_work_date" in indexes
    conn.close()


def test_v3_activity_sessions_migration_preserves_rows_and_is_idempotent(tmp_path):
    db = tmp_path / "migration.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE schema_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        INSERT INTO schema_meta(key, value) VALUES('schema_version', '3');
        CREATE TABLE activity_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            start_time TEXT NOT NULL,
            end_time TEXT NOT NULL,
            date TEXT NOT NULL,
            process_name TEXT,
            exe_path TEXT,
            window_title TEXT,
            normalized_title TEXT,
            category_key TEXT,
            category_name TEXT,
            active_rule TEXT,
            duration_seconds INTEGER DEFAULT 0,
            effective_seconds INTEGER DEFAULT 0,
            idle_seconds INTEGER DEFAULT 0,
            switch_reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO activity_sessions(
            session_id, start_time, end_time, date, duration_seconds,
            effective_seconds, idle_seconds
        ) VALUES(
            'legacy-session', '2026-08-11 09:00:00',
            '2026-08-11 09:05:00', '2026-08-11', 300, 240, 60
        );
        """
    )
    conn.commit()
    conn.close()

    migrated = init_db(str(db))
    row = migrated.execute(
        "SELECT session_id, duration_seconds, effective_seconds, idle_seconds, "
        "engaged_seconds, passive_seconds, metric_version, "
        "classification_version FROM activity_sessions"
    ).fetchone()
    assert row == (
        "legacy-session",
        300,
        240,
        60,
        0,
        0,
        "legacy",
        "legacy",
    )
    assert migrated.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0] == "4"
    indexes = {
        row[1]
        for row in migrated.execute("PRAGMA index_list(activity_sessions)")
    }
    assert "idx_sessions_engaged_work_date" in indexes
    migrated.close()

    reopened = init_db(str(db))
    assert reopened.execute(
        "SELECT COUNT(*) FROM activity_sessions WHERE session_id='legacy-session'"
    ).fetchone()[0] == 1
    assert reopened.execute(
        "SELECT value FROM schema_meta WHERE key='schema_version'"
    ).fetchone()[0] == "4"
    reopened.close()


def test_init_db_closes_connection_when_setup_fails(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
):
    class FailingConnection:
        closed = False

        def execute(self, sql):
            if "journal_mode" in sql:
                raise sqlite3.OperationalError("database is locked")
            return self

        def close(self):
            self.closed = True

    connection = FailingConnection()
    monkeypatch.setattr(
        connection_repository,
        "recover_stale_wal",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        connection_repository.sqlite3,
        "connect",
        lambda *_args, **_kwargs: connection,
    )

    with pytest.raises(sqlite3.OperationalError, match="locked"):
        init_db(str(tmp_path / "locked.db"))

    assert connection.closed is True


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
    assert version == "4"
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
    ).fetchone()[0] == "4"
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
