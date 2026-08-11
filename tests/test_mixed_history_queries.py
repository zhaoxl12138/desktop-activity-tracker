from __future__ import annotations

from datetime import datetime, timedelta

from daylens import database
from daylens.services.trusted_metrics_service import assess_range
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
            engaged_seconds=120,
            passive_seconds=60,
            classification_version="rules-a",
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
    assert result["daily"][0]["engaged_seconds"] == 0
    assert result["daily"][0]["passive_seconds"] == 0
    assert result["daily"][0]["metric_versions"] == ["legacy"]
    assert result["daily"][1]["engaged_seconds"] == 120
    assert result["daily"][1]["passive_seconds"] == 60
    assert result["totals"]["engaged_seconds"] == 120
    assert result["totals"]["passive_seconds"] == 60
    assert result["totals"]["work_engaged_seconds"] == 0
    assert result["totals"]["session_count"] == 1
    assert result["totals"]["legacy_session_count"] == 0
    assert result["totals"]["legacy_log_sample_count"] == 1
    assert result["totals"]["session_anomaly_count"] == 0
    assert result["totals"]["legacy_log_anomaly_count"] == 0
    assert result["totals"]["legacy_granularity_unknown"] is True
    assert result["totals"]["anomaly_count"] == 0
    assert result["totals"]["dates_with_data"] == [yesterday, today]
    assert result["totals"]["metric_versions"] == ["attention-v1", "legacy"]
    assert result["totals"]["classification_versions"] == ["legacy", "rules-a"]

    legacy_day = database.query_date_stats(str(db_path), yesterday)
    assert legacy_day["totals"]["session_count"] == 0
    assert legacy_day["totals"]["legacy_session_count"] == 0
    assert legacy_day["totals"]["legacy_log_sample_count"] == 1
    assert legacy_day["totals"]["legacy_granularity_unknown"] is True


def test_raw_log_samples_never_impersonate_legacy_sessions(tmp_path):
    db_path = tmp_path / "usage.db"
    yesterday, today = _build_mixed_history(db_path)
    conn = database.init_db(str(db_path))
    for index in range(99):
        database.insert_activity_log(
            conn,
            {
                "timestamp": f"{yesterday} 13:{index // 60:02d}:{index % 60:02d}",
                "date": yesterday,
                "process_name": "legacy.exe",
                "window_title": "Legacy sample",
                "category_key": "coding",
                "category_name": "Coding",
                "active_rule": "interactive_required",
                "is_user_active": True,
                "is_effective": True,
                "idle_seconds": 0,
                "duration_seconds": "oops" if index == 0 else 1,
            },
        )
    database.close_db(conn)

    result = database.query_date_range_stats(str(db_path), [yesterday, today])
    trust = assess_range(result["totals"], [yesterday, today])

    assert result["totals"]["session_count"] == 1
    assert result["totals"]["legacy_session_count"] == 0
    assert result["totals"]["legacy_log_sample_count"] == 100
    assert result["totals"]["session_anomaly_count"] == 0
    assert result["totals"]["legacy_log_anomaly_count"] == 1
    assert result["totals"]["anomaly_count"] == 1
    assert result["totals"]["legacy_granularity_unknown"] is True
    assert trust["level"] == "low"
    assert trust["anomaly_ratio"] == 0.0
    assert trust["reasons"] == [
        "旧日志缺少会话粒度",
        "旧日志存在异常记录",
    ]

    legacy_day = database.query_date_stats(str(db_path), yesterday)
    raw_only_trust = assess_range(legacy_day["totals"], [yesterday])
    assert legacy_day["totals"]["session_count"] == 0
    assert legacy_day["totals"]["session_anomaly_count"] == 0
    assert legacy_day["totals"]["legacy_log_anomaly_count"] == 1
    assert raw_only_trust["anomaly_ratio"] == 0.0
    assert raw_only_trust["reasons"] == [
        "旧日志缺少会话粒度",
        "旧日志存在异常记录",
    ]


def test_entertainment_trend_preserves_legacy_dates_when_sessions_exist(tmp_path):
    db_path = tmp_path / "usage.db"
    yesterday, today = _build_mixed_history(db_path)

    result = database.query_entertainment_trend(str(db_path), days=2)

    assert result == [
        {"date": yesterday, "entertainment_seconds": 120},
        {"date": today, "entertainment_seconds": 180},
    ]


def test_entertainment_trend_merges_uncovered_same_day_legacy_video(tmp_path):
    db_path = tmp_path / "usage.db"
    today = datetime.now().replace(hour=10, minute=0, second=0, microsecond=0)
    conn = database.init_db(str(db_path))
    database.insert_session(
        conn,
        ActivitySession(
            session_id="trend-session",
            start_time=today,
            end_time=today + timedelta(seconds=60),
            date=today.strftime("%Y-%m-%d"),
            process_name="player.exe",
            exe_path="C:/player.exe",
            window_title="Current",
            normalized_title="Current",
            category_key="video",
            category_name="娱乐休闲",
            active_rule="passive_allowed",
            duration_seconds=60,
            effective_seconds=60,
            engaged_seconds=0,
            passive_seconds=60,
            classification_version="rules-a",
        ),
    )
    for timestamp, seconds in (
        (today + timedelta(seconds=30), 30),
        (today + timedelta(hours=1), 120),
    ):
        database.insert_activity_log(
            conn,
            {
                "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "date": today.strftime("%Y-%m-%d"),
                "process_name": "legacy-player.exe",
                "window_title": "Legacy video",
                "category_key": "video",
                "category_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "is_user_active": True,
                "is_effective": True,
                "idle_seconds": 0,
                "duration_seconds": seconds,
            },
        )
    database.close_db(conn)

    result = database.query_entertainment_trend(str(db_path), days=1)

    assert result == [
        {
            "date": today.strftime("%Y-%m-%d"),
            "entertainment_seconds": 180,
        }
    ]


def _insert_same_day_session(
    conn,
    *,
    session_id="same-day",
    start_time="2026-08-10 10:00:00",
    end_time="2026-08-10 10:01:00",
    duration_seconds=60,
):
    conn.execute(
        """
        INSERT INTO activity_sessions (
            session_id, start_time, end_time, date, process_name,
            normalized_title, category_key, category_name, active_rule,
            duration_seconds, effective_seconds, engaged_seconds,
            passive_seconds, idle_seconds, metric_version,
            classification_version
        ) VALUES (?, ?, ?, '2026-08-10', 'code.exe', 'main.py', 'coding',
                  '编程开发', 'interactive_required', ?, ?, ?, 0, 0,
                  'attention-v1', 'rules-a')
        """,
        (
            session_id,
            start_time,
            end_time,
            duration_seconds,
            duration_seconds,
            duration_seconds,
        ),
    )


def _insert_same_day_log(conn, timestamp, duration_seconds=60):
    conn.execute(
        """
        INSERT INTO activity_logs (
            timestamp, date, process_name, window_title, category_key,
            category_name, active_rule, is_user_active, is_effective,
            idle_seconds, duration_seconds
        ) VALUES (?, '2026-08-10', 'legacy.exe', 'Legacy', 'other', '其他',
                  'interactive_required', 1, 1, 0, ?)
        """,
        (timestamp, duration_seconds),
    )


def test_same_day_sessions_keep_only_nonoverlapping_legacy_time(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    _insert_same_day_session(conn)
    _insert_same_day_log(conn, "2026-08-10 11:00:00", 120)
    conn.commit()
    database.close_db(conn)

    daily = database.query_date_stats(str(db_path), "2026-08-10")
    date_range = database.query_date_range_stats(
        str(db_path),
        ["2026-08-10"],
    )
    trust = assess_range(daily["totals"], ["2026-08-10"])

    assert daily["totals"]["effective_seconds"] == 180
    assert daily["totals"]["total_seconds"] == 180
    assert daily["totals"]["total_samples"] == 2
    assert daily["totals"]["session_count"] == 1
    assert daily["totals"]["legacy_log_sample_count"] == 1
    assert daily["totals"]["legacy_granularity_unknown"] is True
    assert daily["totals"]["metric_versions"] == ["attention-v1", "legacy"]
    assert trust["level"] == "low"
    assert trust["reasons"][0] == "旧日志缺少会话粒度"
    assert date_range["daily"][0]["effective_seconds"] == 180
    assert date_range["totals"]["effective_seconds"] == 180
    assert date_range["totals"]["legacy_log_sample_count"] == 1


def test_same_day_log_at_session_boundaries_is_not_double_counted(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    _insert_same_day_session(conn)
    for timestamp in (
        "2026-08-10 10:00:00",
        "2026-08-10 10:00:30",
        "2026-08-10 10:01:00",
    ):
        _insert_same_day_log(conn, timestamp, 30)
    _insert_same_day_log(conn, "2026-08-10 10:01:01", 120)
    conn.commit()
    database.close_db(conn)

    daily = database.query_date_stats(str(db_path), "2026-08-10")
    date_range = database.query_date_range_stats(
        str(db_path),
        ["2026-08-10"],
    )

    assert daily["totals"]["effective_seconds"] == 180
    assert daily["totals"]["legacy_log_sample_count"] == 1
    assert date_range["totals"]["effective_seconds"] == 180
    assert date_range["totals"]["legacy_log_sample_count"] == 1


def test_malformed_session_interval_does_not_hide_legacy_logs(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    _insert_same_day_session(
        conn,
        session_id="malformed",
        start_time="not-a-time",
        end_time="also-not-a-time",
    )
    _insert_same_day_log(conn, "2026-08-10 10:00:30", 120)
    conn.commit()
    database.close_db(conn)

    daily = database.query_date_stats(str(db_path), "2026-08-10")
    date_range = database.query_date_range_stats(
        str(db_path),
        ["2026-08-10"],
    )

    assert daily["totals"]["effective_seconds"] == 180
    assert daily["totals"]["legacy_log_sample_count"] == 1
    assert daily["totals"]["session_anomaly_count"] == 1
    assert date_range["totals"]["effective_seconds"] == 180
    assert date_range["totals"]["legacy_log_sample_count"] == 1
    assert date_range["totals"]["session_anomaly_count"] == 1
