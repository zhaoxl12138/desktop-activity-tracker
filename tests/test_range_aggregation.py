from __future__ import annotations

import sqlite3

from daylens import database
from daylens.services.trusted_metrics_service import assess_range


def _insert_trusted_session(
    conn,
    *,
    session_id: str,
    date: str = "2026-07-20",
    start_time: str = "2026-07-20 10:00:00",
    end_time: str = "2026-07-20 10:01:40",
    category_key: str = "coding",
    duration_seconds: int = 100,
    effective_seconds: int = 90,
    engaged_seconds: int = 90,
    passive_seconds: int = 0,
    idle_seconds: int = 10,
    metric_version: str = "attention-v1",
    classification_version: str = "rules-a",
) -> None:
    conn.execute(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,normalized_title,
             category_key,category_name,duration_seconds,effective_seconds,
             engaged_seconds,passive_seconds,idle_seconds,metric_version,
             classification_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            start_time,
            end_time,
            date,
            f"{category_key}.exe",
            session_id,
            category_key,
            category_key,
            duration_seconds,
            effective_seconds,
            engaged_seconds,
            passive_seconds,
            idle_seconds,
            metric_version,
            classification_version,
        ),
    )


def test_daily_trusted_summaries_preserve_exact_subwindow_health_fields():
    prior_dates = [
        "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-01",
        "2026-08-02", "2026-08-03", "2026-08-04",
    ]
    recent_dates = [
        "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-08",
        "2026-08-09", "2026-08-10", "2026-08-11",
    ]
    daily = [
        {
            "date": "2026-07-20",
            "engaged_seconds": 999,
            "passive_seconds": 0,
            "work_engaged_seconds": 999,
            "session_count": 1,
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "legacy_granularity_unknown": False,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "dates_with_data": ["2026-07-20"],
            "metric_versions": ["attention-v2"],
            "classification_versions": ["rules-outside"],
        },
        {
            "date": "2026-08-04",
            "engaged_seconds": 100,
            "passive_seconds": 20,
            "work_engaged_seconds": 80,
            "session_count": 2,
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "legacy_granularity_unknown": False,
            "session_anomaly_count": 1,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 1,
            "dates_with_data": ["2026-08-04"],
            "metric_versions": ["attention-v1"],
            "classification_versions": ["rules-a"],
        },
        {
            "date": "2026-08-05",
            "engaged_seconds": 0,
            "passive_seconds": 0,
            "work_engaged_seconds": 0,
            "session_count": 1,
            "legacy_session_count": 1,
            "legacy_log_sample_count": 0,
            "legacy_granularity_unknown": False,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "dates_with_data": ["2026-08-05"],
            "metric_versions": ["legacy"],
            "classification_versions": ["legacy"],
        },
        {
            "date": "2026-08-06",
            "engaged_seconds": 0,
            "passive_seconds": 0,
            "work_engaged_seconds": 0,
            "session_count": 0,
            "legacy_session_count": 0,
            "legacy_log_sample_count": 2,
            "legacy_granularity_unknown": True,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 1,
            "anomaly_count": 1,
            "dates_with_data": ["2026-08-06"],
            "metric_versions": ["legacy"],
            "classification_versions": ["legacy"],
        },
        {
            "date": "2026-08-11",
            "engaged_seconds": 200,
            "passive_seconds": 40,
            "work_engaged_seconds": 150,
            "session_count": 1,
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "legacy_granularity_unknown": False,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "dates_with_data": ["2026-08-11"],
            "metric_versions": ["attention-v1"],
            "classification_versions": ["rules-b"],
        },
    ]

    prior = database.summarize_daily_trusted_metrics(daily, prior_dates)
    recent = database.summarize_daily_trusted_metrics(daily, recent_dates)
    combined = database.summarize_daily_trusted_metrics(
        daily,
        [*prior_dates, *recent_dates],
    )

    assert prior["engaged_seconds"] == 100
    assert prior["session_count"] == 2
    assert prior["session_anomaly_count"] == 1
    assert prior["anomaly_count"] == 1
    assert prior["metric_versions"] == ["attention-v1"]
    assert prior["classification_versions"] == ["rules-a"]
    assert recent["engaged_seconds"] == 200
    assert recent["work_engaged_seconds"] == 150
    assert recent["session_count"] == 2
    assert recent["legacy_session_count"] == 1
    assert recent["legacy_log_sample_count"] == 2
    assert recent["legacy_granularity_unknown"] is True
    assert recent["legacy_log_anomaly_count"] == 1
    assert recent["anomaly_count"] == 1
    assert recent["metric_versions"] == ["attention-v1", "legacy"]
    assert recent["classification_versions"] == ["legacy", "rules-b"]
    assert combined["engaged_seconds"] == 300
    assert combined["passive_seconds"] == 60
    assert combined["work_engaged_seconds"] == 230
    assert combined["session_count"] == 4
    assert combined["anomaly_count"] == 2
    assert "attention-v2" not in combined["metric_versions"]


def test_date_and_range_summaries_include_trusted_attention_fields(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(conn, session_id="coding")
    _insert_trusted_session(
        conn,
        session_id="video",
        start_time="2026-07-20 11:00:00",
        end_time="2026-07-20 11:01:30",
        category_key="video",
        duration_seconds=90,
        effective_seconds=90,
        engaged_seconds=30,
        passive_seconds=60,
        idle_seconds=0,
    )
    conn.commit()
    conn.close()

    day = database.query_date_stats(str(db_path), "2026-07-20")
    date_range = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    expected = {
        "engaged_seconds": 120,
        "passive_seconds": 60,
        "work_engaged_seconds": 90,
        "session_count": 2,
        "legacy_session_count": 0,
        "session_anomaly_count": 0,
        "legacy_log_anomaly_count": 0,
        "anomaly_count": 0,
        "dates_with_data": ["2026-07-20"],
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
    }
    for key, value in expected.items():
        assert day["totals"][key] == value
        assert date_range["totals"][key] == value
        assert date_range["daily"][0][key] == value
    assert day["totals"]["effective_seconds"] == 180
    assert date_range["totals"]["effective_seconds"] == 180


def test_range_summary_sorts_and_deduplicates_version_sets(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(
        conn,
        session_id="newer",
        metric_version="attention-v2",
        classification_version="rules-b",
    )
    _insert_trusted_session(
        conn,
        session_id="older",
        start_time="2026-07-20 11:00:00",
        end_time="2026-07-20 11:01:40",
        metric_version="attention-v1",
        classification_version="rules-a",
    )
    _insert_trusted_session(
        conn,
        session_id="duplicate-version",
        start_time="2026-07-20 12:00:00",
        end_time="2026-07-20 12:01:40",
        metric_version="attention-v1",
        classification_version="rules-a",
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert result["totals"]["metric_versions"] == [
        "attention-v1",
        "attention-v2",
    ]
    assert result["totals"]["classification_versions"] == [
        "rules-a",
        "rules-b",
    ]


def test_range_dates_preserve_first_seen_order_without_double_counting(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(conn, session_id="first-date")
    _insert_trusted_session(
        conn,
        session_id="second-date",
        date="2026-07-21",
        start_time="2026-07-21 10:00:00",
        end_time="2026-07-21 10:01:40",
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-07-21", "2026-07-20", "2026-07-21"],
    )

    assert result["dates"] == ["2026-07-21", "2026-07-20"]
    assert [row["date"] for row in result["daily"]] == result["dates"]
    assert result["totals"]["effective_seconds"] == 180
    assert result["totals"]["session_count"] == 2


def test_session_anomalies_use_strict_composition_and_wall_clock_tolerance(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(conn, session_id="clean")
    _insert_trusted_session(
        conn,
        session_id="one-second-composition-error",
        start_time="2026-07-20 11:00:00",
        end_time="2026-07-20 11:00:10",
        duration_seconds=10,
        effective_seconds=9,
        engaged_seconds=9,
        idle_seconds=0,
    )
    _insert_trusted_session(
        conn,
        session_id="composition",
        start_time="2026-07-20 12:00:00",
        end_time="2026-07-20 12:00:10",
        duration_seconds=10,
        effective_seconds=8,
        engaged_seconds=8,
        idle_seconds=0,
    )
    _insert_trusted_session(
        conn,
        session_id="negative",
        start_time="2026-07-20 13:00:00",
        end_time="2026-07-20 13:00:00",
        duration_seconds=-1,
        effective_seconds=0,
        engaged_seconds=0,
        idle_seconds=0,
    )
    _insert_trusted_session(
        conn,
        session_id="wall-clock",
        start_time="2026-07-20 14:00:00",
        end_time="2026-07-20 14:10:00",
        duration_seconds=10,
        effective_seconds=10,
        engaged_seconds=10,
        idle_seconds=0,
    )
    for hour in (15, 16):
        _insert_trusted_session(
            conn,
            session_id="duplicate-id",
            start_time=f"2026-07-20 {hour}:00:00",
            end_time=f"2026-07-20 {hour}:00:10",
            duration_seconds=10,
            effective_seconds=10,
            engaged_seconds=10,
            idle_seconds=0,
        )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert result["totals"]["session_count"] == 7
    assert result["totals"]["session_anomaly_count"] == 5
    assert result["totals"]["legacy_log_anomaly_count"] == 0
    assert result["totals"]["anomaly_count"] == 5


def test_malformed_session_values_are_anomalies_without_breaking_query(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    malformed_rows = [
        ("invalid-string", "2026-07-20 10:00:00", "2026-07-20 10:00:00", "oops"),
        ("missing-number", "2026-07-20 11:00:00", "2026-07-20 11:00:00", None),
        ("non-finite", "2026-07-20 12:00:00", "2026-07-20 12:00:00", float("inf")),
        ("bad-iso", "not-a-time", "2026-07-20 13:00:00", 0),
        (
            "mixed-timezones",
            "2026-07-20 14:00:00+00:00",
            "2026-07-20 14:00:00",
            0,
        ),
        ("backwards", "2026-07-20 16:00:00", "2026-07-20 15:00:00", 0),
    ]
    for session_id, start_time, end_time, duration in malformed_rows:
        _insert_trusted_session(
            conn,
            session_id=session_id,
            start_time=start_time,
            end_time=end_time,
            duration_seconds=duration,
            effective_seconds=0,
            engaged_seconds=0,
            passive_seconds=0,
            idle_seconds=0,
        )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert result["totals"]["session_count"] == 6
    assert result["totals"]["session_anomaly_count"] == 6
    assert result["totals"]["anomaly_count"] == 6


def test_legacy_session_still_checks_basic_wall_clock_damage(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(
        conn,
        session_id="legacy-bad-wall-clock",
        start_time="broken",
        end_time="2026-07-20 10:00:00",
        duration_seconds=600,
        effective_seconds=600,
        engaged_seconds=0,
        passive_seconds=0,
        idle_seconds=0,
        metric_version="legacy",
        classification_version="legacy",
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert result["totals"]["session_anomaly_count"] == 1
    assert result["totals"]["anomaly_count"] == 1


def test_composition_tolerance_is_fixed_when_sampling_setting_changes(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(
        conn,
        session_id="one-second-composition-error",
        start_time="2026-07-20 10:00:00",
        end_time="2026-07-20 10:00:30",
        duration_seconds=30,
        effective_seconds=31,
        engaged_seconds=31,
        idle_seconds=0,
    )
    conn.commit()
    conn.close()

    before = database.query_date_range_stats(str(db_path), ["2026-07-20"])
    database.save_settings(str(db_path), {"sample_interval_seconds": 60})
    after = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert before["totals"]["anomaly_count"] == 1
    assert after["totals"]["anomaly_count"] == 1


def test_effective_compatibility_tolerance_is_fixed_when_setting_changes(
    tmp_path,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(
        conn,
        session_id="one-second-effective-error",
        start_time="2026-07-20 10:00:00",
        end_time="2026-07-20 10:00:30",
        duration_seconds=30,
        effective_seconds=31,
        engaged_seconds=20,
        passive_seconds=10,
        idle_seconds=0,
    )
    conn.commit()
    conn.close()

    before = database.query_date_range_stats(str(db_path), ["2026-07-20"])
    database.save_settings(str(db_path), {"sample_interval_seconds": 60})
    after = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert before["totals"]["anomaly_count"] == 1
    assert after["totals"]["anomaly_count"] == 1


def test_legacy_sessions_are_not_anomalous_only_for_missing_new_counters(
    tmp_path,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    _insert_trusted_session(
        conn,
        session_id="legacy",
        start_time="2026-07-20 10:00:00",
        end_time="2026-07-20 10:10:00",
        duration_seconds=600,
        effective_seconds=600,
        engaged_seconds=0,
        passive_seconds=0,
        idle_seconds=0,
        metric_version="legacy",
        classification_version="legacy",
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])

    assert result["totals"]["engaged_seconds"] == 0
    assert result["totals"]["passive_seconds"] == 0
    assert result["totals"]["legacy_session_count"] == 1
    assert result["totals"]["session_anomaly_count"] == 0
    assert result["totals"]["legacy_log_anomaly_count"] == 0
    assert result["totals"]["anomaly_count"] == 0


def test_one_percent_legacy_history_is_medium_trust_in_real_aggregation(
    tmp_path,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    for index in range(99):
        _insert_trusted_session(
            conn,
            session_id=f"new-{index}",
        )
    _insert_trusted_session(
        conn,
        session_id="legacy",
        duration_seconds=100,
        effective_seconds=90,
        engaged_seconds=0,
        passive_seconds=0,
        idle_seconds=0,
        metric_version="legacy",
        classification_version="legacy",
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(str(db_path), ["2026-07-20"])
    trust = assess_range(result["totals"], ["2026-07-20"])

    assert result["totals"]["session_count"] == 100
    assert result["totals"]["legacy_session_count"] == 1
    assert result["totals"]["metric_versions"] == ["attention-v1", "legacy"]
    assert trust["level"] == "medium"
    assert trust["legacy_ratio"] == 0.01


def test_range_stats_keep_process_and_category_as_separate_dimensions(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,normalized_title,
             category_key,category_name,duration_seconds,effective_seconds,
             idle_seconds)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                "youtube",
                "2026-07-20 10:00:00",
                "2026-07-20 10:10:00",
                "2026-07-20",
                "chrome.exe",
                "YouTube",
                "video",
                "娱乐休闲",
                600,
                600,
                0,
            ),
            (
                "github",
                "2026-07-20 11:00:00",
                "2026-07-20 11:10:00",
                "2026-07-20",
                "chrome.exe",
                "GitHub",
                "coding",
                "工作学习",
                600,
                600,
                0,
            ),
        ],
    )
    conn.commit()
    conn.close()

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-07-20"],
    )

    browser_rows = [
        row for row in result["by_app"]
        if row["process_name"] == "chrome.exe"
    ]
    assert {
        (row["category_key"], row["effective_seconds"])
        for row in browser_rows
    } == {("video", 600), ("coding", 600)}


def test_legacy_range_uses_same_work_and_entertainment_category_sets(tmp_path):
    db_path = tmp_path / "usage.db"
    conn = database.init_db(str(db_path))
    for index, (category_key, seconds) in enumerate(
        [("office", 120), ("creative", 180), ("gaming", 240)]
    ):
        database.insert_activity_log(
            conn,
            {
                "timestamp": f"2026-07-19 10:0{index}:00",
                "date": "2026-07-19",
                "process_name": f"{category_key}.exe",
                "window_title": category_key,
                "category_key": category_key,
                "category_name": category_key,
                "active_rule": "interactive_required",
                "is_user_active": True,
                "is_effective": True,
                "idle_seconds": 0,
                "duration_seconds": seconds,
            },
        )
    database.close_db(conn)

    result = database.query_date_range_stats(
        str(db_path),
        ["2026-07-19"],
    )

    assert result["totals"]["work_seconds"] == 300
    assert result["totals"]["video_seconds"] == 240
