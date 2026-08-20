from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from daylens import database
from daylens.repositories import stats_repository
from daylens.services.dashboard_service import load_today_snapshot


def _insert_work_session(
    db_path: Path,
    *,
    session_id: str,
    date_str: str,
    engaged_seconds: int,
    start_time: str | None = None,
    end_time: str | None = None,
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,category_key,
             category_name,duration_seconds,effective_seconds,
             engaged_seconds,passive_seconds,idle_seconds,metric_version,
             classification_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            start_time or f"{date_str} 09:00:00",
            end_time or f"{date_str} 10:00:00",
            date_str,
            "Code.exe",
            "coding",
            "工作学习",
            3_600,
            3_600,
            engaged_seconds,
            0,
            max(0, 3_600 - engaged_seconds),
            "attention-v1" if engaged_seconds else "legacy",
            "rules-a" if engaged_seconds else "legacy",
        ),
    )
    conn.commit()
    conn.close()


def _insert_raw_work_session(
    db_path: Path,
    *,
    session_id: str,
    date_str: str,
    engaged_seconds,
    duration_seconds=3_600,
    effective_seconds=3_600,
    passive_seconds=0,
    idle_seconds=0,
    metric_version="attention-v1",
) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,category_key,
             category_name,duration_seconds,effective_seconds,
             engaged_seconds,passive_seconds,idle_seconds,metric_version,
             classification_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            f"{date_str} 09:00:00",
            f"{date_str} 10:00:00",
            date_str,
            "Code.exe",
            "coding",
            "工作学习",
            duration_seconds,
            effective_seconds,
            engaged_seconds,
            passive_seconds,
            idle_seconds,
            metric_version,
            "rules-a",
        ),
    )
    conn.commit()
    conn.close()


def test_consecutive_days_skips_noncanonical_historical_dates(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    _insert_work_session(
        db_path,
        session_id="today",
        date_str=today.isoformat(),
        engaged_seconds=3_600,
    )
    _insert_work_session(
        db_path,
        session_id="bad-date",
        date_str="0000-bad",
        engaged_seconds=3_600,
        start_time="0000-bad 09:00:00",
        end_time="0000-bad 10:00:00",
    )

    assert database.count_consecutive_days(str(db_path)) == 1


def test_recording_streak_counts_legacy_days_without_changing_focus_streak(
    tmp_path: Path,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    for offset, engaged in ((0, 3_600), (1, 0), (2, 0)):
        _insert_work_session(
            db_path,
            session_id=f"day-{offset}",
            date_str=(today - timedelta(days=offset)).isoformat(),
            engaged_seconds=engaged,
        )

    assert database.count_recording_days(str(db_path)) == 3
    assert database.count_consecutive_days(str(db_path)) == 1

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )
    assert snapshot["recording_streak_days"] == 3
    assert snapshot["consecutive_days"] == 1


def test_bad_historical_date_cannot_break_dashboard_snapshot(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    _insert_work_session(
        db_path,
        session_id="today",
        date_str=today.isoformat(),
        engaged_seconds=3_600,
    )
    _insert_work_session(
        db_path,
        session_id="bad-date",
        date_str="0000-bad",
        engaged_seconds=3_600,
        start_time="bad-start",
        end_time="bad-end",
    )

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["today"] == today.isoformat()
    assert snapshot["consecutive_days"] == 1
    assert "focus_summary" in snapshot


def test_consecutive_days_streams_and_stops_at_first_valid_gap():
    today = datetime.now().date()
    rows = [
        _valid_streaming_row(today.isoformat()),
        _valid_streaming_row("0000-bad"),
        _valid_streaming_row((today - timedelta(days=1)).isoformat()),
        _valid_streaming_row((today - timedelta(days=3)).isoformat()),
    ]

    class StreamingCursor:
        def __iter__(self):
            yield from rows
            raise AssertionError("rows after the first valid gap were consumed")

        def fetchall(self):
            raise AssertionError("consecutive-day reads must stream")

    class FakeConnection:
        def execute(self, _sql, _params):
            return StreamingCursor()

    @contextmanager
    def fake_read_conn(_db_path):
        yield FakeConnection()

    assert stats_repository.count_consecutive_days(
        fake_read_conn,
        "unused.db",
    ) == 2


def _valid_streaming_row(date_str: str) -> dict:
    return {
        "date": date_str,
        "start_time": f"{date_str} 09:00:00",
        "end_time": f"{date_str} 10:00:00",
        "duration_seconds": 3_600,
        "effective_seconds": 3_600,
        "engaged_seconds": 3_600,
        "passive_seconds": 0,
        "idle_seconds": 0,
        "metric_version": "attention-v1",
        "category_key": "coding",
    }


def test_consecutive_days_only_counts_strict_current_engaged_rows(tmp_path: Path):
    today = datetime.now().date().isoformat()
    cases = [
        ("text", "bad", 3_600, 3_600, 0, 0, "attention-v1", 0),
        ("nan-text", "NaN", 3_600, 3_600, 0, 0, "attention-v1", 0),
        ("float", 3_600.5, 3_600, 3_600, 0, 0, "attention-v1", 0),
        # SQLite persists Python booleans as INTEGER.  Conservation still
        # prevents a one-second boolean-shaped counter from creating a day.
        ("bool", True, 3_600, 3_600, 0, 0, "attention-v1", 0),
        ("legacy", 3_600, 3_600, 3_600, 0, 0, "legacy", 0),
        ("not-conserved", 1_800, 3_600, 3_600, 0, 0, "attention-v1", 0),
        ("valid", 3_600, 3_600, 3_600, 0, 0, "attention-v1", 1),
    ]

    for (
        name,
        engaged,
        duration,
        effective,
        passive,
        idle,
        metric_version,
        expected,
    ) in cases:
        db_path = tmp_path / f"{name}.db"
        database.init_db(str(db_path)).close()
        _insert_raw_work_session(
            db_path,
            session_id=name,
            date_str=today,
            engaged_seconds=engaged,
            duration_seconds=duration,
            effective_seconds=effective,
            passive_seconds=passive,
            idle_seconds=idle,
            metric_version=metric_version,
        )

        assert database.count_consecutive_days(str(db_path)) == expected

    bool_conn = sqlite3.connect(tmp_path / "bool.db")
    assert bool_conn.execute(
        "SELECT typeof(engaged_seconds) FROM activity_sessions"
    ).fetchone()[0] == "integer"
    bool_conn.close()


def test_dashboard_excludes_malformed_engaged_session_everywhere(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date().isoformat()
    _insert_raw_work_session(
        db_path,
        session_id="not-conserved",
        date_str=today,
        engaged_seconds=3_600,
        duration_seconds=3_600,
        effective_seconds=3_600,
        passive_seconds=0,
        idle_seconds=3_600,
    )

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["sessions"] == []
    assert snapshot["focus_summary"] == "今日暂未识别到连续专注时段。"
    assert snapshot["consecutive_days"] == 0
    assert snapshot["trust"]["level"] == "low"


def test_consecutive_days_query_uses_partial_date_index(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    index_names = {
        row[1]
        for row in conn.execute("PRAGMA index_list(activity_sessions)")
    }
    query = getattr(stats_repository, "_CONSECUTIVE_DAYS_QUERY", "")
    plan = [
        str(row[3])
        for row in conn.execute(
            f"EXPLAIN QUERY PLAN {query}",
            (datetime.now().strftime("%Y-%m-%d"),),
        )
    ] if query else []
    conn.close()

    assert "idx_sessions_valid_engaged_work_date_v2" in index_names
    assert any(
        "idx_sessions_valid_engaged_work_date_v2" in detail
        for detail in plan
    )
    assert not any("TEMP B-TREE" in detail for detail in plan)

    conn = database.init_db(str(db_path))
    definition = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='index' AND name=?",
        ("idx_sessions_valid_engaged_work_date_v2",),
    ).fetchone()[0]
    conn.close()
    assert "typeof(engaged_seconds) = 'integer'" in definition
    assert "metric_version = 'attention-v1'" in definition
    assert "duration_seconds = engaged_seconds + passive_seconds + idle_seconds" in definition
