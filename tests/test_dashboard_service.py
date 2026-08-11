from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database  # noqa: E402
from daylens.services import dashboard_service  # noqa: E402
from daylens.services.dashboard_service import (  # noqa: E402
    _build_interruptions_section,
    _build_workflow_section,
    _rolling_date_strings,
    build_day_over_day_comparison,
    build_distribution_sections,
    build_hourly_series,
    build_top_app_rows,
    load_today_snapshot,
)
from datetime import date, datetime


def test_distribution_sections_exclude_tools_from_primary_breakdown():
    stats = {
        "by_category": [
            {"category_key": "coding", "effective_seconds": 7200},
            {"category_key": "social", "effective_seconds": 1200},
            {"category_key": "video", "effective_seconds": 1800},
            {"category_key": "tools", "effective_seconds": 900},
        ]
    }

    sections = build_distribution_sections(stats, effective_seconds=11100)

    assert [item["category_key"] for item in sections] == ["work", "video", "social", "other"]
    assert sections[-1]["seconds"] == 900


def test_day_over_day_comparison_encodes_trend_direction():
    today = {
        "by_category": [
            {"category_key": "coding", "effective_seconds": 3600},
            {"category_key": "social", "effective_seconds": 1200},
            {"category_key": "video", "effective_seconds": 600},
        ]
    }
    yesterday = {
        "by_category": [
            {"category_key": "coding", "effective_seconds": 1800},
            {"category_key": "social", "effective_seconds": 1200},
            {"category_key": "video", "effective_seconds": 1800},
        ]
    }

    comparison = build_day_over_day_comparison(today, yesterday)

    assert comparison["work"]["direction"] == "up"
    assert comparison["social"]["direction"] == "flat"
    assert comparison["entertainment"]["direction"] == "down"


def test_top_app_rows_merge_same_display_name_and_sort():
    stats = {
        "by_app": [
            {"process_name": "Code.exe", "effective_seconds": 2000},
            {"process_name": "Cursor.exe", "effective_seconds": 1000},
            {"process_name": "Code.exe", "effective_seconds": 500},
        ],
        "by_app_detail": [],
    }

    def resolve_display(process_name: str, details: list[dict]) -> str:
        return {"Code.exe": "VS Code", "Cursor.exe": "Cursor"}[process_name]

    rows = build_top_app_rows(stats, resolve_display)

    assert rows[0]["display_name"] == "VS Code"
    assert rows[0]["seconds"] == 2500
    assert rows[1]["display_name"] == "Cursor"


def test_build_hourly_series_splits_effective_time_into_hour_buckets():
    sessions = [
        {
            "start_time": "2026-06-02 09:30:00",
            "end_time": "2026-06-02 10:30:00",
            "effective_seconds": 3600,
        }
    ]

    series = build_hourly_series(sessions)

    assert len(series) == 24
    assert series[9] == 30
    assert series[10] == 30


def test_empty_today_snapshot_exposes_trusted_attention_health(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()

    snapshot = load_today_snapshot(str(db_path), lambda process_name, details: process_name)

    assert snapshot["totals"]["engaged_seconds"] == 0
    assert snapshot["totals"]["passive_seconds"] == 0
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["insight"]["kind"] == "data_health"


def test_session_range_query_reads_attention_rows_once(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,normalized_title,
             category_key,category_name,duration_seconds,effective_seconds,
             engaged_seconds,passive_seconds,idle_seconds,metric_version,
             classification_version)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        [
            (
                "first", "2026-08-10 09:00:00", "2026-08-10 09:10:00",
                "2026-08-10", "Code.exe", "Codex", "coding", "工作学习",
                600, 600, 600, 0, 0, "attention-v1", "rules-a",
            ),
            (
                "second", "2026-08-11 10:00:00", "2026-08-11 10:10:00",
                "2026-08-11", "player.exe", "课程", "video", "娱乐休闲",
                600, 600, 60, 540, 0, "attention-v1", "rules-a",
            ),
        ],
    )
    conn.commit()
    conn.close()

    rows = database.query_sessions_for_dates(
        str(db_path),
        ["2026-08-11", "2026-08-10", "2026-08-11"],
    )

    assert [row["session_id"] for row in rows] == ["first", "second"]
    assert rows[0]["engaged_seconds"] == 600
    assert rows[1]["passive_seconds"] == 540
    assert rows[1]["classification_version"] == "rules-a"


def test_snapshot_builds_exact_trusted_insight_payload_without_daily_session_queries(
    monkeypatch,
):
    class FrozenDateTime(datetime):
        calls = 0

        @classmethod
        def now(cls, tz=None):
            cls.calls += 1
            return cls(2026, 8, 11, 12, 0, 0)

    calls = {"date_stats": 0, "range_stats": [], "today_sessions": 0, "range_sessions": 0}

    def trusted_totals(dates, work_engaged):
        return {
            "effective_seconds": work_engaged,
            "engaged_seconds": work_engaged,
            "passive_seconds": 0,
            "idle_seconds": 0,
            "total_seconds": work_engaged,
            "work_engaged_seconds": work_engaged,
            "session_count": len(dates),
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "legacy_granularity_unknown": False,
            "dates_with_data": list(dates),
            "metric_versions": ["attention-v1"],
            "classification_versions": ["rules-a"],
        }

    def query_date_stats(_db_path, date_str):
        calls["date_stats"] += 1
        is_today = date_str == "2026-08-11"
        return {
            "totals": {
                **trusted_totals([date_str], 60 if is_today else 20),
                "effective_seconds": 80 if is_today else 20,
                "engaged_seconds": 60 if is_today else 20,
                "passive_seconds": 20 if is_today else 0,
                "idle_seconds": 20 if is_today else 0,
                "total_seconds": 100 if is_today else 20,
            },
            "by_category": [],
            "by_app": [],
            "by_app_detail": [],
        }

    def query_range_stats(_db_path, dates):
        dates = list(dates)
        calls["range_stats"].append(dates)
        work_engaged = 14_000 if len(dates) == 14 else 7_000
        return {
            "totals": trusted_totals(dates, work_engaged),
            "daily": [
                {"date": value, "effective_seconds": 0}
                for value in dates
            ],
        }

    sessions = []
    for day in range(5, 12):
        date_str = f"2026-08-{day:02d}"
        sessions.extend(
            [
                {
                    "session_id": f"chat-{day}",
                    "date": date_str,
                    "start_time": f"{date_str} 09:00:00",
                    "end_time": f"{date_str} 09:30:00",
                    "process_name": "ChatGPT.exe",
                    "normalized_title": "ChatGPT",
                    "category_key": "ai_tools",
                    "category_name": "工作学习",
                    "duration_seconds": 1_800,
                    "effective_seconds": 1_800,
                    "engaged_seconds": 1_800,
                    "passive_seconds": 0,
                    "idle_seconds": 0,
                    "metric_version": "attention-v1",
                    "classification_version": "rules-a",
                },
                {
                    "session_id": f"codex-{day}",
                    "date": date_str,
                    "start_time": f"{date_str} 09:30:00",
                    "end_time": f"{date_str} 10:30:00",
                    "process_name": "Codex.exe",
                    "normalized_title": "Codex",
                    "category_key": "coding",
                    "category_name": "工作学习",
                    "duration_seconds": 1_800,
                    "effective_seconds": 1_800,
                    "engaged_seconds": 1_800,
                    "passive_seconds": 0,
                    "idle_seconds": 0,
                    "metric_version": "attention-v1",
                    "classification_version": "rules-a",
                },
            ]
        )

    def query_range_sessions(_db_path, dates):
        calls["range_sessions"] += 1
        expected = set(dates)
        return [row for row in sessions if row["date"] in expected]

    def query_today_sessions(_db_path, _date_str):
        calls["today_sessions"] += 1
        return []

    captured = {}

    def select_insight(payload):
        captured.update(payload)
        return {"kind": "captured", "confidence": payload["trust"]["level"]}

    monkeypatch.setattr(dashboard_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(dashboard_service.database, "query_date_stats", query_date_stats)
    monkeypatch.setattr(dashboard_service.database, "query_date_range_stats", query_range_stats)
    monkeypatch.setattr(dashboard_service.database, "query_today_sessions", query_today_sessions)
    monkeypatch.setattr(
        dashboard_service.database,
        "query_sessions_for_dates",
        query_range_sessions,
        raising=False,
    )
    monkeypatch.setattr(dashboard_service, "build_focus_summary", lambda *_: ("", 0))
    monkeypatch.setattr(dashboard_service, "select_primary_insight", select_insight)

    snapshot = load_today_snapshot("unused.db", lambda process_name, _details: process_name)

    assert FrozenDateTime.calls == 1
    assert calls["today_sessions"] == 0
    assert calls["range_sessions"] == 1
    assert sorted(map(len, calls["range_stats"])) == [7, 7, 14, 30]
    assert snapshot["totals"] == {
        "effective_seconds": 80,
        "engaged_seconds": 60,
        "passive_seconds": 20,
        "idle_seconds": 20,
        "total_seconds": 100,
        "active_ratio": 60,
        "passive_ratio": 20,
        "idle_ratio": 20,
    }
    assert snapshot["trust"]["level"] == "high"
    assert snapshot["comparison"] == {
        "comparable": True,
        "category_comparable": True,
        "reason": "",
    }
    assert captured["date_range"] == ["2026-07-29", "2026-08-11"]
    assert captured["best_window"] == {
        "date_range": ["2026-07-29", "2026-08-11"],
        "workday_count": 7,
        "start_hour": 9,
        "end_hour": 11,
        "window_work_engaged_seconds": 25_200,
        "total_work_engaged_seconds": 25_200,
    }
    assert captured["interruptions"] == {
        "date_range": ["2026-08-05", "2026-08-11"],
        "count": 0,
        "window_minutes": 15,
        "classification_comparable": True,
    }
    assert captured["trend"] == {
        "prior_range": ["2026-07-29", "2026-08-04"],
        "recent_range": ["2026-08-05", "2026-08-11"],
        "recent_work_engaged_seconds": 7_000,
        "prior_work_engaged_seconds": 7_000,
        "comparison_comparable": True,
        "category_comparable": True,
    }
    assert captured["workflow"]["date_range"] == ["2026-08-05", "2026-08-11"]
    assert captured["workflow"]["tools"] == ["ChatGPT", "Codex"]
    assert captured["workflow"]["tool_count"] == 2
    assert captured["workflow"]["switch_count"] == 7
    assert captured["workflow"]["non_work_interruptions"] == 0


def test_interruption_events_are_distinct_when_one_event_touches_two_work_sessions():
    sessions = [
        {
            "session_id": "work-before",
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 09:20:00",
            "category_key": "coding",
        },
        {
            "session_id": "social",
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:25:00",
            "end_time": "2026-08-11 09:30:00",
            "category_key": "social",
        },
        {
            "session_id": "work-after",
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:35:00",
            "end_time": "2026-08-11 10:00:00",
            "category_key": "office",
        },
    ]

    section = _build_interruptions_section(
        sessions,
        ["2026-08-05", "2026-08-11"],
        False,
    )

    assert section["count"] == 1
    assert section["classification_comparable"] is False


def test_workflow_payload_excludes_markup_disguised_as_a_tool_name():
    sessions = [
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 09:10:00",
            "normalized_title": "&lt;b&gt;Injected&lt;/b&gt;",
            "process_name": "chrome.exe",
            "category_key": "coding",
        },
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:10:00",
            "end_time": "2026-08-11 09:20:00",
            "normalized_title": "Codex",
            "process_name": "Codex.exe",
            "category_key": "coding",
        },
    ]

    section = _build_workflow_section(
        sessions,
        ["2026-08-05", "2026-08-11"],
    )

    assert section["tools"] == ["Codex"]
    assert section["tool_count"] == 1
    assert section["switch_count"] == 0


def test_workflow_uses_stable_process_identity_instead_of_document_titles():
    sessions = [
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 09:10:00",
            "normalized_title": "project-a.py",
            "process_name": "Code.exe",
            "category_key": "coding",
        },
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:10:00",
            "end_time": "2026-08-11 09:20:00",
            "normalized_title": "project-b.py",
            "process_name": "Code.exe",
            "category_key": "coding",
        },
    ]

    section = _build_workflow_section(
        sessions,
        ["2026-08-05", "2026-08-11"],
    )

    assert section["tools"] == ["Code"]
    assert section["tool_count"] == 1
    assert section["switch_count"] == 0


def test_insight_failure_hides_only_the_card_and_preserves_trust(
    tmp_path: Path,
    monkeypatch,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    calls = 0

    def fail_insight(_payload):
        nonlocal calls
        calls += 1
        raise RuntimeError("selector unavailable")

    monkeypatch.setattr(dashboard_service, "select_primary_insight", fail_insight)

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert calls == 1
    assert snapshot["insight"] is None
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["trust"]["reasons"][0] == "范围内没有可评估记录"
    assert "统计数据格式异常" not in snapshot["trust"]["reasons"]
    assert snapshot["totals"]["effective_seconds"] == 0


def test_dashboard_trend_ranges_are_rolling_windows():
    today = date(2026, 7, 1)

    assert _rolling_date_strings(today, 7) == [
        "2026-06-25",
        "2026-06-26",
        "2026-06-27",
        "2026-06-28",
        "2026-06-29",
        "2026-06-30",
        "2026-07-01",
    ]
    thirty_days = _rolling_date_strings(today, 30)
    assert len(thirty_days) == 30
    assert thirty_days[0] == "2026-06-02"
    assert thirty_days[-1] == "2026-07-01"
