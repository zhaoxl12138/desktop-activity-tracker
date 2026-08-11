from __future__ import annotations

import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from daylens import database
from daylens.services import command_handlers


V3_SCHEMA = """
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

CREATE TABLE activity_logs (
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

CREATE TABLE schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

INSERT INTO schema_meta(key, value) VALUES('schema_version', '3');
"""


def _create_v3_database(db_path: Path, date_str: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(V3_SCHEMA)
    conn.execute(
        """
        INSERT INTO activity_sessions
            (session_id, start_time, end_time, date, process_name,
             window_title, normalized_title, category_key, category_name,
             active_rule, duration_seconds, effective_seconds, idle_seconds)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "v3-session",
            f"{date_str} 09:00:00",
            f"{date_str} 10:00:00",
            date_str,
            "Code.exe",
            "main.py",
            "main.py",
            "coding",
            "工作学习",
            "interactive_required",
            3_600,
            3_600,
            0,
        ),
    )
    conn.commit()
    conn.close()


def _invoke_read_handler(
    handler_name: str,
    config: dict,
    reports_dir: Path,
    now: datetime,
) -> None:
    if handler_name == "report":
        command_handlers.handle_report(
            config,
            SimpleNamespace(today=True, date=None),
        )
    elif handler_name == "today":
        command_handlers.handle_today(config)
    elif handler_name == "export":
        command_handlers.handle_export(
            config,
            SimpleNamespace(date=now.strftime("%Y-%m-%d"), format="csv"),
            str(reports_dir),
        )
    elif handler_name == "weekly":
        command_handlers.handle_weekly(
            config,
            SimpleNamespace(year=now.year, week=now.isocalendar().week),
            str(reports_dir),
        )
    elif handler_name == "monthly":
        command_handlers.handle_monthly(
            config,
            SimpleNamespace(year=now.year, month=now.month),
            str(reports_dir),
        )
    else:  # pragma: no cover - parametrization guard
        raise AssertionError(handler_name)


@pytest.mark.parametrize(
    "handler_name",
    ["report", "today", "export", "weekly", "monthly"],
)
def test_cli_read_handlers_migrate_real_v3_database_before_querying(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    handler_name: str,
) -> None:
    now = datetime.now()
    db_path = tmp_path / f"{handler_name}.db"
    reports_dir = tmp_path / "reports"
    _create_v3_database(db_path, now.strftime("%Y-%m-%d"))

    real_init_db = database.init_db
    migration_connections = []

    def tracked_init_db(path: str):
        conn = real_init_db(path)
        migration_connections.append(conn)
        return conn

    monkeypatch.setattr(command_handlers.database, "init_db", tracked_init_db)

    _invoke_read_handler(
        handler_name,
        {"db_path": str(db_path)},
        reports_dir,
        now,
    )

    output = capsys.readouterr()
    assert "ERROR" not in output.out
    assert "no such column" not in output.out
    assert migration_connections
    for conn in migration_connections:
        with pytest.raises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    conn = sqlite3.connect(db_path)
    row = conn.execute(
        """
        SELECT engaged_seconds, passive_seconds, metric_version,
               classification_version
        FROM activity_sessions
        """
    ).fetchone()
    row_count = conn.execute(
        "SELECT COUNT(*) FROM activity_sessions"
    ).fetchone()[0]
    schema_version = conn.execute(
        "SELECT value FROM schema_meta WHERE key = 'schema_version'"
    ).fetchone()[0]
    conn.close()

    assert row_count == 1
    assert row == (0, 0, "legacy", "legacy")
    assert schema_version == "4"


def test_cli_schema_migration_is_safe_when_readers_start_together(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "concurrent-v3.db"
    _create_v3_database(db_path, datetime.now().strftime("%Y-%m-%d"))
    barrier = threading.Barrier(4)

    def migrate() -> None:
        barrier.wait()
        command_handlers._migrate_existing_db(str(db_path))

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(migrate) for _ in range(4)]
        for future in futures:
            future.result()

    conn = sqlite3.connect(db_path)
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(activity_sessions)")
    }
    row_count = conn.execute(
        "SELECT COUNT(*) FROM activity_sessions"
    ).fetchone()[0]
    journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    conn.close()

    assert {
        "engaged_seconds",
        "passive_seconds",
        "metric_version",
        "classification_version",
    }.issubset(columns)
    assert row_count == 1
    assert journal_mode == "wal"


@pytest.mark.parametrize(
    "handler_name",
    ["report", "today", "export", "weekly", "monthly"],
)
def test_cli_read_handlers_keep_missing_database_behavior(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    handler_name: str,
) -> None:
    db_path = tmp_path / "missing.db"

    def fail_if_initialized(_path: str):  # pragma: no cover - assertion helper
        raise AssertionError("missing databases must not be created by reads")

    monkeypatch.setattr(
        command_handlers.database,
        "init_db",
        fail_if_initialized,
    )

    _invoke_read_handler(
        handler_name,
        {"db_path": str(db_path)},
        tmp_path / "reports",
        datetime.now(),
    )

    assert not db_path.exists()
    assert "数据库不存在" in capsys.readouterr().out
