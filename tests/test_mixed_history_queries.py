from __future__ import annotations

from datetime import datetime, timedelta

from daylens import database
from daylens.session_tracker import ActivitySession


def _build_mixed_history(db_path):
    today = datetime.now().replace(hour=12, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)
    conn = database.init_db(str(db_path))
    database.insert_activity_log(
        conn,
        {
            "timestamp": yesterday.strftime("%Y-%m-%d %H:%M:%S"),
            "date": yesterday.strftime("%Y-%m-%d"),
            "process_name": "legacy-player.exe",
            "window_title": "Legacy video",
            "category_key": "video",
            "category_name": "娱乐休闲",
            "active_rule": "passive_allowed",
            "is_user_active": True,
            "is_effective": True,
            "idle_seconds": 0,
            "duration_seconds": 120,
        },
    )
    database.insert_session(
        conn,
        ActivitySession(
            session_id="today-video",
            start_time=today,
            end_time=today + timedelta(seconds=180),
            date=today.strftime("%Y-%m-%d"),
            process_name="player.exe",
            exe_path="C:/player.exe",
            window_title="Today video",
            normalized_title="Today video",
            category_key="video",
            category_name="娱乐休闲",
            active_rule="passive_allowed",
            duration_seconds=180,
            effective_seconds=180,
        ),
    )
    database.close_db(conn)
    return yesterday.strftime("%Y-%m-%d"), today.strftime("%Y-%m-%d")


def test_date_range_preserves_legacy_dates_when_sessions_exist(tmp_path):
    db_path = tmp_path / "usage.db"
    yesterday, today = _build_mixed_history(db_path)

    result = database.query_date_range_stats(str(db_path), [yesterday, today])

    assert [row["effective_seconds"] for row in result["daily"]] == [120, 180]
    assert result["totals"]["effective_seconds"] == 300
    assert result["totals"]["video_seconds"] == 300


def test_entertainment_trend_preserves_legacy_dates_when_sessions_exist(tmp_path):
    db_path = tmp_path / "usage.db"
    yesterday, today = _build_mixed_history(db_path)

    result = database.query_entertainment_trend(str(db_path), days=2)

    assert result == [
        {"date": yesterday, "entertainment_seconds": 120},
        {"date": today, "entertainment_seconds": 180},
    ]
