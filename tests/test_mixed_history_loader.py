from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from daylens import database
from daylens.repositories import stats_repository


def _new_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    return db_path


def _insert_session(
    conn,
    *,
    session_id: str,
    date_str: str,
    start_time: str,
    end_time: str,
    duration: int = 60,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_sessions (
            session_id, start_time, end_time, date, process_name,
            normalized_title, category_key, category_name, active_rule,
            duration_seconds, effective_seconds, engaged_seconds,
            passive_seconds, idle_seconds, metric_version,
            classification_version
        ) VALUES (?, ?, ?, ?, 'code.exe', 'main.py', 'coding', '编程开发',
                  'interactive_required', ?, ?, ?, 0, 0,
                  'attention-v1', 'rules-a')
        """,
        (
            session_id,
            start_time,
            end_time,
            date_str,
            duration,
            duration,
            duration,
        ),
    )


def _insert_log(
    conn,
    *,
    date_str: str,
    timestamp: str,
    duration: int = 120,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_logs (
            timestamp, date, process_name, window_title, category_key,
            category_name, active_rule, is_user_active, is_effective,
            idle_seconds, duration_seconds
        ) VALUES (?, ?, 'legacy.exe', 'Legacy', 'other', '其他',
                  'interactive_required', 1, 1, 0, ?)
        """,
        (timestamp, date_str, duration),
    )


def test_empty_range_uses_the_public_range_shape():
    result = stats_repository.query_date_range_stats(
        lambda _path: pytest.fail("empty ranges must not read the database"),
        "unused.db",
        [],
    )

    assert result == {
        "dates": [],
        "daily": [],
        "by_category": [],
        "by_app": [],
        "totals": {
            "effective_seconds": 0,
            "idle_seconds": 0,
            "total_seconds": 0,
            "work_seconds": 0,
            "video_seconds": 0,
            "engaged_seconds": 0,
            "passive_seconds": 0,
            "work_engaged_seconds": 0,
            "session_count": 0,
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "legacy_granularity_unknown": False,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "dates_with_data": [],
            "metric_versions": [],
            "classification_versions": [],
        },
    }


@pytest.mark.parametrize(
    ("date_str", "start_time", "end_time", "log_timestamp"),
    [
        (
            "2026-08-10",
            "2026-08-10  10:00:00",
            "2026-08-10 10:01:00",
            "2026-08-10 10:00:30",
        ),
        (
            "2026-08-10",
            "2026-08-10 24:00:00",
            "2026-08-11 00:01:00",
            "2026-08-11 00:00:30",
        ),
        (
            "2026-02-28",
            "2026-02-30 10:00:00",
            "2026-03-02 10:01:00",
            "2026-03-02 10:00:30",
        ),
        (
            "2026-08-10",
            "2026-08-10 10:00:00+08:00",
            "2026-08-10 10:01:00",
            "2026-08-10 10:00:30",
        ),
    ],
)
def test_sqlite_permissive_session_times_do_not_cover_legacy_logs(
    tmp_path: Path,
    date_str: str,
    start_time: str,
    end_time: str,
    log_timestamp: str,
):
    db_path = _new_database(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_session(
            conn,
            session_id="invalid-time",
            date_str=date_str,
            start_time=start_time,
            end_time=end_time,
        )
        _insert_log(conn, date_str=date_str, timestamp=log_timestamp)

    result = database.query_date_stats(str(db_path), date_str)

    assert result["totals"]["effective_seconds"] == 180
    assert result["totals"]["session_anomaly_count"] == 1
    assert result["totals"]["legacy_log_sample_count"] == 1


def test_noncanonical_legacy_timestamp_is_not_treated_as_covered(tmp_path: Path):
    db_path = _new_database(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_session(
            conn,
            session_id="valid-time",
            date_str="2026-08-10",
            start_time="2026-08-10 10:00:00",
            end_time="2026-08-10 10:01:00",
        )
        _insert_log(
            conn,
            date_str="2026-08-10",
            timestamp="2026-08-10  10:00:30",
        )

    result = database.query_date_stats(str(db_path), "2026-08-10")

    assert result["totals"]["effective_seconds"] == 180
    assert result["totals"]["legacy_log_sample_count"] == 1
    assert result["totals"]["legacy_log_anomaly_count"] == 1


def test_aware_and_naive_timestamps_are_not_mixed_for_coverage(tmp_path: Path):
    db_path = _new_database(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_session(
            conn,
            session_id="aware",
            date_str="2026-08-10",
            start_time="2026-08-10 10:00:00+08:00",
            end_time="2026-08-10 10:01:00+08:00",
        )
        _insert_log(
            conn,
            date_str="2026-08-10",
            timestamp="2026-08-10 10:00:30",
        )
        _insert_log(
            conn,
            date_str="2026-08-10",
            timestamp="2026-08-10 10:00:30+08:00",
            duration=30,
        )

    result = database.query_date_stats(str(db_path), "2026-08-10")

    assert result["totals"]["effective_seconds"] == 180
    assert result["totals"]["legacy_log_sample_count"] == 1


def test_cross_midnight_session_covers_only_its_attributed_date(tmp_path: Path):
    db_path = _new_database(tmp_path)
    with sqlite3.connect(db_path) as conn:
        _insert_session(
            conn,
            session_id="cross-midnight",
            date_str="2026-08-10",
            start_time="2026-08-10 23:59:30",
            end_time="2026-08-11 00:00:30",
        )
        _insert_log(
            conn,
            date_str="2026-08-10",
            timestamp="2026-08-10 23:59:45",
            duration=30,
        )
        _insert_log(
            conn,
            date_str="2026-08-11",
            timestamp="2026-08-11 00:00:15",
        )

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-08-10", "2026-08-11"],
    )

    assert [row["effective_seconds"] for row in result["daily"]] == [60, 120]
    assert result["totals"]["legacy_log_sample_count"] == 1


class _CountingConnection:
    def __init__(self, connection, statements):
        self._connection = connection
        self._statements = statements

    def execute(self, statement, parameters=()):
        self._statements.append(" ".join(statement.split()))
        return self._connection.execute(statement, parameters)


class _CountingReadContext:
    def __init__(self, db_path: str, statements: list[str]):
        self._db_path = db_path
        self._statements = statements
        self._connection = None

    def __enter__(self):
        self._connection = sqlite3.connect(self._db_path)
        self._connection.row_factory = sqlite3.Row
        return _CountingConnection(self._connection, self._statements)

    def __exit__(self, *_args):
        self._connection.close()


def test_mixed_range_loader_reads_each_source_once_at_scale(tmp_path: Path):
    db_path = _new_database(tmp_path)
    date_str = "2026-08-10"
    base = datetime(2026, 8, 10, 8, 0, 0)
    with sqlite3.connect(db_path) as conn:
        sessions = []
        for index in range(1_000):
            start = base + timedelta(seconds=index * 10)
            end = start + timedelta(seconds=4)
            sessions.append(
                (
                    f"session-{index}",
                    start.strftime("%Y-%m-%d %H:%M:%S"),
                    end.strftime("%Y-%m-%d %H:%M:%S"),
                    date_str,
                    "code.exe",
                    "main.py",
                    "coding",
                    "编程开发",
                    "interactive_required",
                    4,
                    4,
                    4,
                    0,
                    0,
                    "attention-v1",
                    "rules-a",
                )
            )
        conn.executemany(
            """
            INSERT INTO activity_sessions (
                session_id, start_time, end_time, date, process_name,
                normalized_title, category_key, category_name, active_rule,
                duration_seconds, effective_seconds, engaged_seconds,
                passive_seconds, idle_seconds, metric_version,
                classification_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            sessions,
        )
        logs = []
        for index in range(5_000):
            timestamp = base + timedelta(seconds=index * 2)
            logs.append(
                (
                    timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                    date_str,
                    "legacy.exe",
                    "Legacy",
                    "other",
                    "其他",
                    "interactive_required",
                    1,
                    1,
                    0,
                    2,
                )
            )
        conn.executemany(
            """
            INSERT INTO activity_logs (
                timestamp, date, process_name, window_title, category_key,
                category_name, active_rule, is_user_active, is_effective,
                idle_seconds, duration_seconds
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            logs,
        )

    statements: list[str] = []

    def counting_read_conn(path):
        return _CountingReadContext(path, statements)

    started = time.perf_counter()
    result = stats_repository.query_date_range_stats(
        counting_read_conn,
        str(db_path),
        [date_str],
    )
    elapsed = time.perf_counter() - started

    session_reads = [sql for sql in statements if "FROM activity_sessions" in sql]
    log_reads = [sql for sql in statements if "FROM activity_logs" in sql]
    assert len(session_reads) == 1
    assert len(log_reads) == 1
    assert len(statements) == 2
    assert result["totals"]["session_count"] == 1_000
    assert elapsed < 1.5


def test_daily_app_groups_keep_legacy_unbounded_detail_while_range_caps_top_20(
    tmp_path: Path,
):
    db_path = _new_database(tmp_path)
    with sqlite3.connect(db_path) as conn:
        for index in range(21):
            conn.execute(
                """
                INSERT INTO activity_sessions (
                    session_id, start_time, end_time, date, process_name,
                    normalized_title, category_key, category_name,
                    duration_seconds, effective_seconds, engaged_seconds,
                    passive_seconds, idle_seconds, metric_version,
                    classification_version
                ) VALUES (?, '2026-08-10 10:00:00',
                          '2026-08-10 10:01:00', '2026-08-10', ?, 'Title',
                          'coding', '编程开发', 60, 60, 60, 0, 0,
                          'attention-v1', 'rules-a')
                """,
                (f"session-{index}", f"app-{index}.exe"),
            )

    daily = database.query_date_stats(str(db_path), "2026-08-10")
    date_range = database.query_date_range_stats(
        str(db_path),
        ["2026-08-10"],
    )

    assert len(daily["by_app"]) == 21
    assert len(date_range["by_app"]) == 20
