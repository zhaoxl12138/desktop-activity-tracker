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
        {"date": today.isoformat()},
        {"date": "0000-bad"},
        {"date": (today - timedelta(days=1)).isoformat()},
        {"date": (today - timedelta(days=3)).isoformat()},
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

    assert "idx_sessions_engaged_work_date" in index_names
    assert any(
        "idx_sessions_engaged_work_date" in detail
        for detail in plan
    )
    assert not any("TEMP B-TREE" in detail for detail in plan)
