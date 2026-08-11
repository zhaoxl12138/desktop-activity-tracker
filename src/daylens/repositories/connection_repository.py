"""Connection and schema helpers split from the legacy database module."""

from __future__ import annotations

import os
import sqlite3
import threading

WAL_CHECKPOINT_INTERVAL = 100

_shared_read_conn = None
_shared_read_db_path = None
_shared_read_thread_id = None


class TrackedConnection(sqlite3.Connection):
    """SQLite connection subclass that can keep lightweight runtime state."""


SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    process_name TEXT,
    exe_path TEXT,
    window_title TEXT,
    category_key TEXT,
    category_name TEXT,
    active_rule TEXT,
    is_user_active INTEGER,
    is_effective INTEGER,
    idle_seconds REAL,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS activity_sessions (
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
    engaged_seconds INTEGER DEFAULT 0,
    passive_seconds INTEGER DEFAULT 0,
    metric_version TEXT DEFAULT 'legacy',
    classification_version TEXT DEFAULT 'legacy',
    idle_seconds INTEGER DEFAULT 0,
    switch_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category_key TEXT,
    category_name TEXT,
    process_name TEXT,
    total_seconds INTEGER,
    effective_seconds INTEGER,
    idle_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_logs(date);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity_logs(category_key);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON activity_sessions(date);
CREATE INDEX IF NOT EXISTS idx_sessions_category ON activity_sessions(category_key);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON activity_sessions(session_id);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custom_rules (
    category_key TEXT PRIMARY KEY,
    display_name TEXT,
    active_rule TEXT,
    process_names TEXT,
    title_keywords TEXT,
    title_patterns TEXT DEFAULT '',
    process_names_mode TEXT DEFAULT 'inherit',
    title_keywords_mode TEXT DEFAULT 'inherit',
    title_patterns_mode TEXT DEFAULT 'inherit'
);

CREATE TABLE IF NOT EXISTS poetry_lines (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    author TEXT NOT NULL,
    content TEXT NOT NULL UNIQUE,
    origin TEXT,
    category TEXT
);
CREATE INDEX IF NOT EXISTS idx_poetry_author ON poetry_lines(author);
"""


class ReadConnectionContext:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.conn = None
        self.own = False

    def __enter__(self):
        if (
            _shared_read_conn is not None
            and _shared_read_db_path == self.db_path
            and _shared_read_thread_id == threading.get_ident()
        ):
            self.conn = _shared_read_conn
        else:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            self.own = True
        return self.conn

    def __exit__(self, *args):
        if self.own and self.conn is not None:
            self.conn.close()
        return False


def init_shared_read_conn(db_path: str) -> None:
    global _shared_read_conn, _shared_read_db_path, _shared_read_thread_id
    if _shared_read_conn is not None and _shared_read_db_path != db_path:
        _shared_read_conn.close()
        _shared_read_conn = None
    if _shared_read_conn is None:
        _shared_read_conn = sqlite3.connect(db_path)
        _shared_read_conn.row_factory = sqlite3.Row
        _shared_read_conn.execute("PRAGMA journal_mode=WAL")
        _shared_read_db_path = db_path
        _shared_read_thread_id = threading.get_ident()


def close_shared_read_conn() -> None:
    global _shared_read_conn, _shared_read_db_path, _shared_read_thread_id
    if _shared_read_conn:
        _shared_read_conn.close()
        _shared_read_conn = None
        _shared_read_db_path = None
        _shared_read_thread_id = None


def read_conn(db_path: str) -> ReadConnectionContext:
    return ReadConnectionContext(db_path)


def wal_checkpoint(conn) -> None:
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass


def maybe_checkpoint(conn) -> None:
    conn._commit_count = getattr(conn, "_commit_count", 0) + 1
    if conn._commit_count % WAL_CHECKPOINT_INTERVAL == 0:
        wal_checkpoint(conn)


def recover_stale_wal(
    db_path: str,
    *,
    busy_timeout_ms: int = 5000,
) -> None:
    wal_path = db_path + "-wal"
    if not os.path.exists(wal_path):
        return
    conn = None
    try:
        bounded_timeout = max(0, int(busy_timeout_ms))
        conn = sqlite3.connect(
            db_path,
            timeout=bounded_timeout / 1000.0,
        )
        conn.execute(f"PRAGMA busy_timeout={bounded_timeout}")
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if rows:
            busy, _, _ = rows
            if busy == 0:
                conn.close()
    except sqlite3.OperationalError:
        pass
    finally:
        try:
            if conn is not None:
                conn.close()
        except Exception:
            pass


def init_db(db_path: str, *, busy_timeout_ms: int = 5000):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    bounded_timeout = max(0, int(busy_timeout_ms))
    recover_stale_wal(db_path, busy_timeout_ms=bounded_timeout)
    conn = sqlite3.connect(
        db_path,
        factory=TrackedConnection,
        timeout=bounded_timeout / 1000.0,
    )
    try:
        conn.execute(f"PRAGMA busy_timeout={bounded_timeout}")
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(SCHEMA)
        _run_migrations(conn)
        _ensure_runtime_indexes(conn)
        conn.commit()
        conn._commit_count = 0
        return conn
    except Exception:
        conn.close()
        raise


def _run_migrations(conn) -> None:
    """Apply idempotent schema upgrades without rewriting user data."""
    row = conn.execute("SELECT value FROM schema_meta WHERE key = 'schema_version'").fetchone()
    version = int(row[0]) if row and str(row[0]).isdigit() else 0
    if version < 1:
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_date_category ON activity_sessions(date, category_key)")
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', '1') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        version = 1
    if version < 2:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(custom_rules)").fetchall()
        }
        if "title_patterns" not in columns:
            conn.execute(
                "ALTER TABLE custom_rules "
                "ADD COLUMN title_patterns TEXT DEFAULT ''"
            )
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', '2') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        version = 2
    if version < 3:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(custom_rules)").fetchall()
        }
        for column in (
            "process_names_mode",
            "title_keywords_mode",
            "title_patterns_mode",
        ):
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE custom_rules "
                    f"ADD COLUMN {column} TEXT DEFAULT 'inherit'"
                )
        # Legacy title lists had no way to distinguish explicit empty from
        # missing. Preserve non-empty overrides and let empty values inherit.
        # Legacy process lists already had replacement semantics, so preserve
        # removals conservatively across the schema upgrade.
        conn.execute(
            "UPDATE custom_rules SET process_names_mode = 'replace'"
        )
        conn.execute(
            "UPDATE custom_rules SET title_keywords_mode = "
            "CASE WHEN COALESCE(title_keywords, '') <> '' "
            "THEN 'replace' ELSE 'inherit' END"
        )
        conn.execute(
            "UPDATE custom_rules SET title_patterns_mode = "
            "CASE WHEN COALESCE(title_patterns, '') <> '' "
            "THEN 'replace' ELSE 'inherit' END"
        )
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', '3') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        version = 3
    if version < 4:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(activity_sessions)"
            ).fetchall()
        }
        column_definitions = {
            "engaged_seconds": "INTEGER DEFAULT 0",
            "passive_seconds": "INTEGER DEFAULT 0",
            "metric_version": "TEXT DEFAULT 'legacy'",
            "classification_version": "TEXT DEFAULT 'legacy'",
        }
        for column, definition in column_definitions.items():
            if column not in columns:
                conn.execute(
                    f"ALTER TABLE activity_sessions "
                    f"ADD COLUMN {column} {definition}"
                )
        conn.execute(
            "INSERT INTO schema_meta(key, value) VALUES('schema_version', '4') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
    conn.commit()


def _ensure_runtime_indexes(conn) -> None:
    """Create indexes that depend on columns added by migrations."""
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_engaged_work_date "
        "ON activity_sessions(date DESC) "
        "WHERE engaged_seconds > 0 AND category_key IN "
        "('ai_tools','coding','creative','office','reading')"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_sessions_valid_engaged_work_date_v2 "
        "ON activity_sessions(date DESC) "
        "WHERE typeof(engaged_seconds) = 'integer' "
        "AND engaged_seconds > 0 "
        "AND metric_version = 'attention-v1' "
        "AND category_key IN "
        "('ai_tools','coding','creative','office','reading') "
        "AND typeof(duration_seconds) = 'integer' AND duration_seconds >= 0 "
        "AND typeof(effective_seconds) = 'integer' AND effective_seconds >= 0 "
        "AND typeof(passive_seconds) = 'integer' AND passive_seconds >= 0 "
        "AND typeof(idle_seconds) = 'integer' AND idle_seconds >= 0 "
        "AND duration_seconds = engaged_seconds + passive_seconds + idle_seconds "
        "AND effective_seconds = engaged_seconds + passive_seconds"
    )


def close_db(conn) -> None:
    if conn is None:
        return
    try:
        wal_checkpoint(conn)
        conn.close()
    except Exception:
        pass
