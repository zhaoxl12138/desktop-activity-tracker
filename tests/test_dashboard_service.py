from __future__ import annotations

import sys
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database  # noqa: E402
from daylens import timeline  # noqa: E402
from daylens.services import dashboard_service  # noqa: E402
from daylens.services.insights_service import select_primary_insight  # noqa: E402
from daylens.services.dashboard_service import (  # noqa: E402
    _build_interruptions_section,
    _build_thirty_day_trend,
    _build_workflow_section,
    _rolling_date_strings,
    build_day_over_day_comparison,
    build_distribution_sections,
    build_hourly_series,
    build_hourly_series_split,
    build_work_episode_rows,
    build_top_app_rows,
    load_today_snapshot,
)
from datetime import date, datetime, timedelta


def _rhythm_session(
    date_str: str,
    start: str,
    end: str,
    engaged_seconds: int,
    *,
    session_id: str = "work",
    category_key: str = "coding",
) -> dict:
    duration = int(
        (
            datetime.strptime(f"{date_str} {end}", "%Y-%m-%d %H:%M:%S")
            - datetime.strptime(f"{date_str} {start}", "%Y-%m-%d %H:%M:%S")
        ).total_seconds()
    )
    return {
        "session_id": session_id,
        "date": date_str,
        "start_time": f"{date_str} {start}",
        "end_time": f"{date_str} {end}",
        "process_name": "Code.exe",
        "normalized_title": "Codex",
        "category_key": category_key,
        "category_name": "工作学习",
        "duration_seconds": duration,
        "effective_seconds": engaged_seconds,
        "engaged_seconds": engaged_seconds,
        "passive_seconds": 0,
        "idle_seconds": max(0, duration - engaged_seconds),
        "metric_version": "attention-v1",
        "classification_version": "rules-a",
    }


def _trusted_rhythm_day(date_str: str, engaged_seconds: int) -> dict:
    return {
        "date": date_str,
        "effective_seconds": engaged_seconds,
        "engaged_seconds": engaged_seconds,
        "work_engaged_seconds": engaged_seconds,
        "passive_seconds": 0,
        "idle_seconds": 0,
        "total_seconds": engaged_seconds,
        "session_count": 1,
        "legacy_session_count": 0,
        "legacy_log_sample_count": 0,
        "session_anomaly_count": 0,
        "legacy_log_anomaly_count": 0,
        "anomaly_count": 0,
        "legacy_granularity_unknown": False,
        "dates_with_data": [date_str],
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
    }


def test_rhythm_half_hour_cumulative_series_conserves_cross_slot_engagement():
    sessions = [
        _rhythm_session(
            "2026-08-12",
            "09:20:00",
            "10:10:00",
            2_400,
        )
    ]

    buckets = dashboard_service.build_work_engaged_half_hours(
        sessions,
        "2026-08-12",
    )

    assert len(buckets) == 48
    assert sum(buckets) == 2_400
    assert buckets[18:21] == [480, 1_440, 480]


def test_rhythm_half_hours_clip_cross_midnight_session_to_requested_date():
    session = _rhythm_session(
        "2026-08-11",
        "23:50:00",
        "23:59:59",
        600,
    )
    session["end_time"] = "2026-08-12 00:10:00"
    session["duration_seconds"] = 1_200
    session["effective_seconds"] = 1_200
    session["engaged_seconds"] = 1_200

    buckets = dashboard_service.build_work_engaged_half_hours(
        [session],
        "2026-08-11",
    )

    assert sum(buckets) == 600
    assert buckets[47] == 600
    assert buckets[0] == 0


def test_rhythm_today_uses_recent_seven_trusted_same_day_type_baseline():
    today = date(2026, 8, 12)  # Wednesday
    candidate_dates = [today - timedelta(days=offset) for offset in range(1, 31)]
    workdays = [day for day in candidate_dates if day.weekday() < 5][:8]
    sessions = [
        _rhythm_session(today.isoformat(), "09:00:00", "10:00:00", 3_600),
        *[
            _rhythm_session(
                day.isoformat(),
                "09:00:00",
                "10:00:00",
                600 * (index + 1),
                session_id=f"base-{index}",
            )
            for index, day in enumerate(workdays)
        ],
    ]
    daily = [
        _trusted_rhythm_day(day.isoformat(), 600 * (index + 1))
        for index, day in enumerate(workdays)
    ]
    daily.append(_trusted_rhythm_day(today.isoformat(), 3_600))

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 50),
        sessions=sessions,
        daily_rows=daily,
        query_failed=False,
    )

    current = rhythm["today"]
    assert current["comparison"]["sample_count"] == 7
    assert current["status"]["label"] == "基线7天"
    assert len(current["chart"]["current"]) == 48
    assert current["chart"]["current"][29] == 3_600
    assert current["chart"]["current"][30:] == [None] * 18
    assert current["chart"]["baseline_median"][29] == 2_400


def test_rhythm_today_hides_comparison_when_metric_history_changed():
    today = date(2026, 8, 12)
    legacy_day = _trusted_rhythm_day("2026-08-11", 3_600)
    legacy_day["metric_versions"] = ["legacy"]
    legacy_day["legacy_session_count"] = 1

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 12, 0),
        sessions=[
            _rhythm_session(today.isoformat(), "09:00:00", "10:00:00", 3_600)
        ],
        daily_rows=[_trusted_rhythm_day(today.isoformat(), 3_600), legacy_day],
        query_failed=False,
    )

    assert rhythm["today"]["comparison"]["comparable"] is False
    assert rhythm["today"]["status"]["label"] == "口径已变化"
    assert rhythm["today"]["chart"]["baseline_median"] == []


def test_rhythm_complete_day_and_week_views_preserve_unknown_gaps():
    today = date(2026, 8, 12)
    complete_dates = [today - timedelta(days=offset) for offset in range(1, 31)]
    daily = [
        _trusted_rhythm_day(day.isoformat(), 3_600 + index * 60)
        for index, day in enumerate(complete_dates)
        if day != date(2026, 8, 8)
    ]

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 0),
        sessions=[],
        daily_rows=daily,
        query_failed=False,
    )

    seven = rhythm["7d"]
    assert seven["date_range"] == ["2026-08-05", "2026-08-11"]
    assert seven["chart"]["values"][3] is None  # 2026-08-08 is unknown.
    assert seven["metrics"][2]["value"] == "6天"
    thirty = rhythm["30d"]
    assert thirty["date_range"] == ["2026-07-13", "2026-08-11"]
    assert len(thirty["chart"]["labels"]) == 5
    assert thirty["chart"]["values"][-1] is None  # Partial week has < 4 trusted days.


@pytest.mark.parametrize(
    ("query_failed", "legacy", "expected"),
    [
        (True, False, "暂不可比较"),
        (False, True, "口径已变化"),
    ],
)
def test_rhythm_all_modes_expose_unavailable_comparison_reason(
    query_failed: bool,
    legacy: bool,
    expected: str,
):
    today = date(2026, 8, 12)
    daily = [
        _trusted_rhythm_day(
            (today - timedelta(days=offset)).isoformat(),
            3_600,
        )
        for offset in range(31)
    ]
    if legacy:
        daily[4]["metric_versions"] = ["legacy"]
        daily[4]["legacy_session_count"] = 1

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 0),
        sessions=[],
        daily_rows=daily,
        query_failed=query_failed,
    )

    assert {rhythm[mode]["status"]["label"] for mode in ("today", "7d", "30d")} == {expected}
    assert all(
        rhythm[mode]["comparison"]["comparable"] is False
        for mode in ("today", "7d", "30d")
    )


def test_rhythm_rejects_daily_rows_with_anomalies_from_baseline():
    today = date(2026, 8, 12)
    days = [today - timedelta(days=offset) for offset in range(1, 9)]
    daily = [_trusted_rhythm_day(day.isoformat(), 3_600) for day in days]
    daily[0]["session_anomaly_count"] = 1
    sessions = [
        _rhythm_session(
            day.isoformat(),
            "09:00:00",
            "10:00:00",
            3_600,
            session_id=f"work-{day}",
        )
        for day in days
    ]

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 0),
        sessions=sessions,
        daily_rows=daily,
        query_failed=False,
    )

    assert rhythm["today"]["comparison"]["sample_count"] == 5


def test_rhythm_classification_break_only_keeps_latest_version_points():
    today = date(2026, 8, 12)
    daily = []
    for offset in reversed(range(31)):
        day = today - timedelta(days=offset)
        row = _trusted_rhythm_day(day.isoformat(), 3_600)
        row["classification_versions"] = [
            "rules-new" if offset <= 5 else "rules-old"
        ]
        daily.append(row)

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 0),
        sessions=[],
        daily_rows=daily,
        query_failed=False,
    )

    assert rhythm["7d"]["chart"]["values"][:2] == [None, None]
    assert rhythm["7d"]["chart"]["values"][2:] == [3_600] * 5
    assert "仅展示当前规则记录" in rhythm["7d"]["conclusion"]
    assert "日均" not in rhythm["7d"]["conclusion"]
    assert "仅展示当前规则记录" in rhythm["30d"]["conclusion"]


def test_rhythm_today_baseline_is_clipped_to_the_same_time_of_day():
    today = date(2026, 8, 12)
    baseline_days = [
        today - timedelta(days=offset)
        for offset in range(1, 6)
        if (today - timedelta(days=offset)).weekday() < 5
    ]
    sessions = [
        _rhythm_session(today.isoformat(), "14:30:00", "14:50:00", 1_200),
        *[
            _rhythm_session(
                day.isoformat(),
                "14:30:00",
                "15:00:00",
                1_800,
                session_id=f"base-{day}",
            )
            for day in baseline_days
        ],
    ]
    daily = [
        _trusted_rhythm_day(day.isoformat(), 1_800)
        for day in baseline_days
    ]

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 50),
        sessions=sessions,
        daily_rows=daily,
        query_failed=False,
    )

    assert rhythm["today"]["comparison"]["delta_seconds"] == 0
    assert rhythm["today"]["chart"]["baseline_median"][29] == 1_200


def test_rhythm_today_baseline_clips_each_session_at_exact_clock_time():
    today = date(2026, 8, 12)
    baseline_days = [date(2026, 8, 11), date(2026, 8, 10), date(2026, 8, 7)]
    sessions = []
    daily = []
    for day in baseline_days:
        sessions.extend(
            [
                _rhythm_session(
                    day.isoformat(),
                    "14:00:00",
                    "14:15:00",
                    900,
                    session_id=f"done-{day}",
                ),
                _rhythm_session(
                    day.isoformat(),
                    "14:45:00",
                    "15:00:00",
                    900,
                    session_id=f"partial-{day}",
                ),
            ]
        )
        daily.append(_trusted_rhythm_day(day.isoformat(), 1_800))

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 50),
        sessions=sessions,
        daily_rows=daily,
        query_failed=False,
    )

    assert rhythm["today"]["chart"]["baseline_median"][29] == 1_200


def test_rhythm_version_break_filters_sessions_to_latest_versions():
    today = date(2026, 8, 12)
    daily = [_trusted_rhythm_day(today.isoformat(), 600)]
    daily[0]["classification_versions"] = ["rules-old", "rules-new"]
    sessions = [
        {
            **_rhythm_session(
                today.isoformat(),
                "09:00:00",
                "10:00:00",
                3_600,
                session_id="old",
            ),
            "classification_version": "rules-old",
            "metric_version": "legacy",
        },
        {
            **_rhythm_session(
                today.isoformat(),
                "10:00:00",
                "10:10:00",
                600,
                session_id="new",
            ),
            "classification_version": "rules-new",
            "metric_version": "attention-v1",
        },
    ]

    rhythm = dashboard_service.build_rhythm_snapshot(
        captured_now=datetime(2026, 8, 12, 14, 0),
        sessions=sessions,
        daily_rows=daily,
        query_failed=False,
    )

    assert rhythm["today"]["chart"]["current"][28] == 600
    assert rhythm["today"]["metrics"][0]["value"] == "10:00"


def test_rhythm_interruption_metric_formats_count_delta():
    assert dashboard_service._count_delta_text(-2) == "比平时少2次"
    assert dashboard_service._count_delta_text(1) == "比平时多1次"
    assert dashboard_service._count_delta_text(0) == "与平时接近"


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


def test_work_episode_rows_merge_short_work_switches_and_conserve_engagement():
    sessions = [
        {
            **_rhythm_session("2026-08-12", "09:00:00", "09:20:00", 1_000),
            "session_id": "codex",
            "process_name": "Codex.exe",
            "normalized_title": "DayLens 首页重构",
        },
        {
            **_rhythm_session("2026-08-12", "09:20:20", "09:35:00", 700),
            "session_id": "chrome",
            "process_name": "chrome.exe",
            "normalized_title": "PySide6 布局资料",
        },
        {
            **_rhythm_session("2026-08-12", "09:40:00", "09:50:00", 500),
            "session_id": "wechat",
            "process_name": "WeChat.exe",
            "normalized_title": "微信",
            "category_key": "social",
        },
        {
            **_rhythm_session("2026-08-12", "10:00:00", "10:10:00", 400),
            "session_id": "code",
            "process_name": "Code.exe",
            "normalized_title": "dashboard_service.py",
        },
    ]

    rows = build_work_episode_rows(
        sessions,
        lambda process, _details: {
            "Codex.exe": "Codex",
            "chrome.exe": "Chrome",
            "Code.exe": "VS Code",
        }.get(process, process),
    )

    assert len(rows) == 2
    assert rows[0]["start_time"] == "2026-08-12 09:00:00"
    assert rows[0]["end_time"] == "2026-08-12 09:35:00"
    assert rows[0]["engaged_seconds"] == 1_700
    assert rows[0]["apps"] == ["Codex", "Chrome"]
    assert rows[0]["topic"] == "DayLens 首页重构"
    assert sum(row["engaged_seconds"] for row in rows) == 2_100


def test_work_episode_rows_skip_malformed_sessions():
    valid = _rhythm_session("2026-08-12", "11:00:00", "11:10:00", 600)
    invalid = {**valid, "session_id": "bad", "start_time": "bad"}

    rows = build_work_episode_rows([invalid, valid], lambda process, _details: process)

    assert len(rows) == 1
    assert rows[0]["engaged_seconds"] == 600


def test_work_episode_rows_split_on_short_non_work_interruption():
    first = {
        **_rhythm_session("2026-08-12", "13:00:00", "13:10:00", 600),
        "session_id": "first",
    }
    interruption = {
        **_rhythm_session("2026-08-12", "13:10:05", "13:10:15", 10),
        "session_id": "social",
        "category_key": "social",
    }
    second = {
        **_rhythm_session("2026-08-12", "13:10:20", "13:20:00", 580),
        "session_id": "second",
    }

    rows = build_work_episode_rows(
        [first, interruption, second], lambda process, _details: process
    )

    assert len(rows) == 2


def test_work_episode_rows_marks_legacy_fallback_as_effective():
    legacy = {
        **_rhythm_session("2026-08-12", "14:00:00", "14:10:00", 600),
        "metric_version": "legacy",
    }
    legacy["engaged_seconds"] = 0

    rows = build_work_episode_rows([legacy], lambda process, _details: process)

    assert rows[0]["seconds"] == 600
    assert rows[0]["metric_label"] == "有效"


def test_top_app_rows_merge_only_stable_process_aliases_and_keep_browsers_separate():
    stats = {
        "by_app": [
            {"process_name": "chrome.exe", "effective_seconds": 600, "engaged_seconds": 500, "passive_seconds": 0},
            {"process_name": " Chrome.EXE ", "effective_seconds": 300, "engaged_seconds": 200, "passive_seconds": 0},
            {"process_name": "360ChromeX.exe", "effective_seconds": 800, "engaged_seconds": 100, "passive_seconds": 600},
        ],
        "by_app_detail": [
            {"process_name": "chrome.exe", "window_title": "RK3568 文档", "effective_seconds": 500},
            {"process_name": " Chrome.EXE ", "window_title": "RK3568 文档", "effective_seconds": 200},
            {"process_name": "360ChromeX.exe", "window_title": "招录页面", "effective_seconds": 700},
        ],
    }

    rows = build_top_app_rows(stats, lambda process, _details: {
        "chrome.exe": "Chrome",
        " Chrome.EXE ": "Chrome",
        "360ChromeX.exe": "360极速浏览器",
    }[process])

    assert [row["display_name"] for row in rows] == ["Chrome", "360极速浏览器"]
    assert rows[0] == {
        "process_name": "chrome.exe",
        "display_name": "Chrome",
        "seconds": 900,
        "engaged_seconds": 700,
        "passive_seconds": 0,
        "purpose": "RK3568 文档",
    }
    assert rows[1]["process_name"] == "360ChromeX.exe"
    assert rows[1]["passive_seconds"] == 600


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


def test_work_hourly_series_uses_engaged_while_total_keeps_effective():
    split = build_hourly_series_split(
        [
            {
                "start_time": "2026-06-02 09:00:00",
                "end_time": "2026-06-02 10:00:00",
                "category_key": "coding",
                "effective_seconds": 3_600,
                "engaged_seconds": 0,
            },
            {
                "start_time": "2026-06-02 10:00:00",
                "end_time": "2026-06-02 11:00:00",
                "category_key": "coding",
                "effective_seconds": 3_600,
                "engaged_seconds": 1_800,
            },
        ]
    )

    assert split["total"][9] == 60
    assert split["work"][9] == 0
    assert split["total"][10] == 60
    assert split["work"][10] == 30


def test_work_hourly_series_preserves_rounded_engaged_minutes_across_hours():
    split = build_hourly_series_split(
        [
            {
                "start_time": "2026-06-02 09:30:00",
                "end_time": "2026-06-02 10:30:00",
                "category_key": "coding",
                "effective_seconds": 1_001,
                "engaged_seconds": 1_001,
            },
            {
                "start_time": "bad-time",
                "end_time": "2026-06-02 12:00:00",
                "category_key": "coding",
                "effective_seconds": 600,
                "engaged_seconds": 600,
            },
            {
                "start_time": "2026-06-02 13:00:00",
                "end_time": "2026-06-02 12:00:00",
                "category_key": "coding",
                "effective_seconds": 600,
                "engaged_seconds": 600,
            },
        ]
    )

    assert sum(split["work"]) == round(1_001 / 60)
    assert split["work"][9] + split["work"][10] == 17
    assert split["total"][9:11] == [8, 8]
    assert sum(split["entertainment"]) == 0


def test_empty_today_snapshot_exposes_trusted_attention_health(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()

    snapshot = load_today_snapshot(str(db_path), lambda process_name, details: process_name)

    assert snapshot["totals"]["engaged_seconds"] == 0
    assert snapshot["totals"]["passive_seconds"] == 0
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["insight"]["kind"] == "data_health"


def test_thirty_day_trend_prefers_engaged_and_marks_new_snapshot_semantics(
    tmp_path: Path,
):
    points = _build_thirty_day_trend(
        [
            {
                "effective_seconds": 3_600,
                "engaged_seconds": 1_800,
                "session_count": 1,
                "legacy_session_count": 0,
                "legacy_log_sample_count": 0,
                "legacy_granularity_unknown": False,
                "metric_versions": ["attention-v1"],
            },
            {
                "effective_seconds": 3_600,
                "engaged_seconds": 0,
                "session_count": 1,
                "legacy_session_count": 1,
                "legacy_log_sample_count": 0,
                "legacy_granularity_unknown": False,
                "metric_versions": ["legacy"],
            },
        ]
    )

    assert points == [0.5, None]

    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["totals"]["primary_metric"] == "engaged"
    assert snapshot["trend"]["thirty_day_metric"] == "engaged"


def test_thirty_day_trend_distinguishes_empty_legacy_mixed_and_current_days():
    points = _build_thirty_day_trend(
        [
            {
                "date": "2026-08-08",
                "effective_seconds": 0,
                "engaged_seconds": 0,
                "session_count": 0,
                "legacy_log_sample_count": 0,
                "metric_versions": [],
            },
            {
                "date": "2026-08-09",
                "effective_seconds": 3_600,
                "engaged_seconds": 0,
                "session_count": 1,
                "legacy_session_count": 1,
                "legacy_log_sample_count": 0,
                "metric_versions": ["legacy"],
            },
            {
                "date": "2026-08-10",
                "effective_seconds": 3_600,
                "engaged_seconds": 1_800,
                "session_count": 2,
                "legacy_session_count": 1,
                "legacy_log_sample_count": 1,
                "legacy_granularity_unknown": True,
                "metric_versions": ["attention-v1", "legacy"],
            },
            {
                "date": "2026-08-11",
                "effective_seconds": 3_600,
                "engaged_seconds": 2_700,
                "session_count": 1,
                "legacy_session_count": 0,
                "legacy_log_sample_count": 0,
                "legacy_granularity_unknown": False,
                "metric_versions": ["attention-v1"],
            },
            {
                "date": "2026-08-12",
                "effective_seconds": "unknown",
                "engaged_seconds": 0,
                "session_count": 0,
                "legacy_log_sample_count": 0,
                "metric_versions": [],
            },
        ]
    )

    assert points == [0.0, None, None, 0.8, None]


def test_snapshot_marks_full_thirty_day_metric_break_even_when_recent_trust_is_high(
    tmp_path: Path,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    dates = [today - timedelta(days=offset) for offset in reversed(range(30))]
    conn = sqlite3.connect(db_path)
    for index, day in enumerate(dates):
        date_str = day.strftime("%Y-%m-%d")
        legacy = index < 16
        conn.execute(
            """
            INSERT INTO activity_sessions
                (session_id,start_time,end_time,date,process_name,
                 normalized_title,category_key,category_name,
                 duration_seconds,effective_seconds,engaged_seconds,
                 passive_seconds,idle_seconds,metric_version,
                 classification_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"session-{index}",
                f"{date_str} 09:00:00",
                f"{date_str} 10:00:00",
                date_str,
                "Code.exe",
                "main.py",
                "coding",
                "工作学习",
                3_600,
                3_600,
                0 if legacy else 3_600,
                0,
                0,
                "legacy" if legacy else "attention-v1",
                "legacy" if legacy else "rules-a",
            ),
        )
    conn.commit()
    conn.close()

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["trust"]["level"] == "high"
    assert snapshot["trend"]["thirty_days"][:16] == [None] * 16
    assert snapshot["trend"]["thirty_days"][16:] == [1.0] * 14
    assert snapshot["trend"]["thirty_day_metric_break"] is True
    assert snapshot["trend"]["thirty_day_classification_break"] is True
    assert snapshot["trend"]["thirty_day_notice"] == (
        "计量口径已变化，历史参与趋势暂不可比"
    )


@pytest.mark.parametrize(
    ("legacy_days", "expected_break", "expected_notice", "expected_point"),
    [
        (0, False, "", 1.0),
        (
            30,
            True,
            "计量口径已变化，历史参与趋势暂不可比",
            None,
        ),
    ],
)
def test_snapshot_notice_covers_all_current_and_all_legacy_history(
    tmp_path: Path,
    legacy_days: int,
    expected_break: bool,
    expected_notice: str,
    expected_point: float | None,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    conn = sqlite3.connect(db_path)
    for index, offset in enumerate(reversed(range(30))):
        day = today - timedelta(days=offset)
        date_str = day.strftime("%Y-%m-%d")
        legacy = index < legacy_days
        conn.execute(
            """
            INSERT INTO activity_sessions
                (session_id,start_time,end_time,date,process_name,
                 category_key,category_name,duration_seconds,
                 effective_seconds,engaged_seconds,passive_seconds,
                 idle_seconds,metric_version,classification_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                f"day-{index}",
                f"{date_str} 09:00:00",
                f"{date_str} 10:00:00",
                date_str,
                "Code.exe",
                "coding",
                "工作学习",
                3_600,
                3_600,
                0 if legacy else 3_600,
                0,
                0,
                "legacy" if legacy else "attention-v1",
                "legacy" if legacy else "rules-a",
            ),
        )
    conn.commit()
    conn.close()

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["trend"]["thirty_day_metric_break"] is expected_break
    assert snapshot["trend"]["thirty_day_classification_break"] is False
    assert snapshot["trend"]["thirty_day_notice"] == expected_notice
    assert snapshot["trend"]["thirty_days"] == [expected_point] * 30


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


def test_real_database_malformed_sessions_keep_dashboard_available(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().strftime("%Y-%m-%d")
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
                "bad-number", f"{today} 09:00:00", f"{today} 09:05:00",
                today, "Code.exe", "bad number", "coding", "工作学习",
                300, "bad", 300, 0, 0, "attention-v1", "rules-a",
            ),
            (
                "infinite", f"{today} 10:00:00", f"{today} 11:00:00",
                today, "Code.exe", "infinite", "coding", "工作学习",
                3_600, 3_600, float("inf"), 0, 0, "attention-v1", "rules-a",
            ),
            (
                "bad-time", "not-a-time", f"{today} 11:01:00",
                today, "Code.exe", "bad time", "coding", "工作学习",
                60, 60, 60, 0, 0, "attention-v1", "rules-a",
            ),
        ],
    )
    conn.commit()
    conn.close()

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["today"] == today
    assert snapshot["sessions"] == []
    assert len(snapshot["trend"]["today"]) == 24
    assert "暂未识别" in snapshot["focus_summary"]
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["insight"]["kind"] == "data_health"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("duration_seconds", "bad"),
        ("effective_seconds", float("nan")),
        ("engaged_seconds", float("inf")),
        ("passive_seconds", float("-inf")),
        ("idle_seconds", True),
        ("start_time", "bad-time"),
        ("end_time", "bad-time"),
    ],
)
def test_injected_malformed_session_forces_low_trust_and_is_skipped(
    monkeypatch,
    field,
    value,
):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 8, 11, 12, 0, 0)

    def trusted_day(date_str, has_data):
        return {
            "date": date_str,
            "effective_seconds": 60 if has_data else 0,
            "engaged_seconds": 60 if has_data else 0,
            "passive_seconds": 0,
            "idle_seconds": 0,
            "total_seconds": 60 if has_data else 0,
            "work_engaged_seconds": 60 if has_data else 0,
            "session_count": int(has_data),
            "legacy_session_count": 0,
            "legacy_log_sample_count": 0,
            "session_anomaly_count": 0,
            "legacy_log_anomaly_count": 0,
            "anomaly_count": 0,
            "legacy_granularity_unknown": False,
            "dates_with_data": [date_str] if has_data else [],
            "metric_versions": ["attention-v1"] if has_data else [],
            "classification_versions": ["rules-a"] if has_data else [],
        }

    def query_range_stats(_db_path, dates):
        dates = list(dates)
        daily = [
            trusted_day(date_str, index >= len(dates) - 14)
            for index, date_str in enumerate(dates)
        ]
        return {"daily": daily, "totals": {}}

    safe_stats = {
        "totals": {
            "effective_seconds": 60,
            "engaged_seconds": 60,
            "passive_seconds": 0,
            "idle_seconds": 0,
            "total_seconds": 60,
        },
        "by_category": [],
        "by_app": [],
        "by_app_detail": [],
    }
    malformed = {
        "session_id": "injected",
        "date": "2026-08-11",
        "start_time": "2026-08-11 09:00:00",
        "end_time": "2026-08-11 09:01:00",
        "process_name": "Code.exe",
        "normalized_title": "Codex",
        "category_key": "coding",
        "category_name": "工作学习",
        "duration_seconds": 60,
        "effective_seconds": 60,
        "engaged_seconds": 60,
        "passive_seconds": 0,
        "idle_seconds": 0,
        "metric_version": "attention-v1",
        "classification_version": "rules-a",
        field: value,
    }

    monkeypatch.setattr(dashboard_service, "datetime", FrozenDateTime)
    monkeypatch.setattr(
        dashboard_service.database,
        "query_date_stats",
        lambda *_: safe_stats,
    )
    monkeypatch.setattr(
        dashboard_service.database,
        "query_date_range_stats",
        query_range_stats,
    )
    monkeypatch.setattr(
        dashboard_service.database,
        "query_sessions_for_dates",
        lambda *_: [malformed],
    )
    monkeypatch.setattr(
        dashboard_service,
        "build_focus_summary",
        lambda *_: ("", 0),
    )

    snapshot = load_today_snapshot(
        "unused.db",
        lambda process_name, _details: process_name,
    )

    assert snapshot["sessions"] == []
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["insight"]["kind"] == "data_health"


def test_timeline_skips_malformed_session_rows(monkeypatch):
    rows = [
        {
            "session_id": "bad-number",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 09:10:00",
            "process_name": "Code.exe",
            "window_title": "",
            "normalized_title": "Codex",
            "category_key": "coding",
            "category_name": "工作学习",
            "duration_seconds": 600,
            "effective_seconds": float("inf"),
            "engaged_seconds": 600,
            "passive_seconds": 0,
            "idle_seconds": 0,
        },
        {
            "session_id": "bad-time",
            "start_time": "not-a-time",
            "end_time": "2026-08-11 10:10:00",
            "process_name": "Code.exe",
            "window_title": "",
            "normalized_title": "Codex",
            "category_key": "coding",
            "category_name": "工作学习",
            "duration_seconds": 600,
            "effective_seconds": 600,
            "engaged_seconds": 600,
            "passive_seconds": 0,
            "idle_seconds": 0,
        },
    ]
    monkeypatch.setattr(timeline.database, "query_timeline_sessions", lambda *_: rows)

    blocks = timeline.build_timeline("unused.db", "2026-08-11")

    assert len(blocks) == 48
    assert sum(block.effective_seconds for block in blocks) == 0


def test_legacy_effective_time_does_not_create_engaged_work_or_focus(
    monkeypatch,
):
    rows = [
        {
            "session_id": "legacy-work",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 10:00:00",
            "process_name": "Code.exe",
            "window_title": "",
            "normalized_title": "main.py",
            "category_key": "coding",
            "category_name": "工作学习",
            "duration_seconds": 3_600,
            "effective_seconds": 3_600,
            "engaged_seconds": 0,
            "passive_seconds": 0,
            "idle_seconds": 0,
        }
    ]
    monkeypatch.setattr(
        timeline.database,
        "query_timeline_sessions",
        lambda *_: rows,
    )

    blocks = timeline.build_timeline("unused.db", "2026-08-11")

    assert sum(block.effective_seconds for block in blocks) == 3_600
    assert sum(block.engaged_seconds for block in blocks) == 0
    assert sum(block.work_seconds for block in blocks) == 0
    assert timeline.identify_focus_blocks(blocks) == []


def test_attention_engaged_work_creates_focus_but_passive_video_does_not(
    monkeypatch,
):
    rows = [
        {
            "session_id": "attention-work",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 10:00:00",
            "process_name": "Code.exe",
            "window_title": "",
            "normalized_title": "main.py",
            "category_key": "coding",
            "category_name": "工作学习",
            "duration_seconds": 3_600,
            "effective_seconds": 3_600,
            "engaged_seconds": 3_600,
            "passive_seconds": 0,
            "idle_seconds": 0,
        },
        {
            "session_id": "passive-video",
            "start_time": "2026-08-11 10:00:00",
            "end_time": "2026-08-11 11:00:00",
            "process_name": "player.exe",
            "window_title": "",
            "normalized_title": "course",
            "category_key": "video",
            "category_name": "娱乐休闲",
            "duration_seconds": 3_600,
            "effective_seconds": 3_600,
            "engaged_seconds": 0,
            "passive_seconds": 3_600,
            "idle_seconds": 0,
        },
    ]
    monkeypatch.setattr(
        timeline.database,
        "query_timeline_sessions",
        lambda *_: rows,
    )

    blocks = timeline.build_timeline("unused.db", "2026-08-11")
    focus_blocks = timeline.identify_focus_blocks(blocks)

    assert sum(block.engaged_seconds for block in blocks) == 3_600
    assert sum(block.work_seconds for block in blocks) == 3_600
    assert len(focus_blocks) == 1
    assert focus_blocks[0].effective_seconds == 3_600


def test_cross_hour_engaged_allocation_preserves_session_total(
    monkeypatch,
):
    rows = [
        {
            "session_id": "cross-hour",
            "start_time": "2026-08-11 09:45:00",
            "end_time": "2026-08-11 10:15:00",
            "process_name": "Code.exe",
            "window_title": "",
            "normalized_title": "main.py",
            "category_key": "coding",
            "category_name": "工作学习",
            "duration_seconds": 1_800,
            "effective_seconds": 1_001,
            "engaged_seconds": 1_001,
            "passive_seconds": 0,
            "idle_seconds": 799,
        }
    ]
    monkeypatch.setattr(
        timeline.database,
        "query_timeline_sessions",
        lambda *_: rows,
    )

    blocks = timeline.build_timeline("unused.db", "2026-08-11")

    assert sum(block.engaged_seconds for block in blocks) == 1_001
    assert sum(block.work_seconds for block in blocks) == 1_001
    assert blocks[19].engaged_seconds + blocks[20].engaged_seconds == 1_001


def test_consecutive_focus_days_require_engaged_work(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = datetime.now().date()
    yesterday = today - timedelta(days=1)
    conn = sqlite3.connect(db_path)
    for session_id, day in (("today", today), ("yesterday", yesterday)):
        date_str = day.strftime("%Y-%m-%d")
        conn.execute(
            """
            INSERT INTO activity_sessions
                (session_id,start_time,end_time,date,process_name,
                 category_key,category_name,duration_seconds,
                 effective_seconds,engaged_seconds,passive_seconds,
                 idle_seconds,metric_version,classification_version)
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
                3_600,
                3_600,
                0,
                0,
                0,
                "legacy",
                "legacy",
            ),
        )
    conn.commit()

    assert database.count_consecutive_days(str(db_path)) == 0

    conn.execute(
        """
        UPDATE activity_sessions
        SET engaged_seconds = 3600, metric_version = 'attention-v1',
            classification_version = 'rules-a'
        """
    )
    conn.commit()
    conn.close()

    assert database.count_consecutive_days(str(db_path)) == 2


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
                {
                    "date": value,
                    "effective_seconds": 0,
                    **trusted_totals([value], 1_000),
                }
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
                    "duration_seconds": 3_600,
                    "effective_seconds": 1_800,
                    "engaged_seconds": 1_800,
                    "passive_seconds": 0,
                    "idle_seconds": 1_800,
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
    assert [len(dates) for dates in calls["range_stats"]] == [31]
    assert snapshot["rhythm"]["version"] == 1
    assert snapshot["rhythm"]["primary_metric"] == "work_engaged_seconds"
    assert snapshot["rhythm"]["today"]["chart"]["kind"] == "cumulative"
    assert snapshot["rhythm"]["7d"]["date_range"] == [
        "2026-08-04",
        "2026-08-10",
    ]
    assert snapshot["totals"] == {
        "effective_seconds": 80,
        "engaged_seconds": 60,
        "passive_seconds": 20,
        "idle_seconds": 20,
        "total_seconds": 100,
        "active_ratio": 60,
        "passive_ratio": 20,
        "idle_ratio": 20,
        "primary_metric": "engaged",
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


def test_workflow_ignores_title_markup_and_uses_process_identity():
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

    assert section["tools"] == ["chrome", "Codex"]
    assert section["tool_count"] == 2
    assert section["switch_count"] == 1


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


def test_workflow_does_not_turn_browser_titles_into_distinct_tools():
    sessions = [
        {
            "date": "2026-08-11",
            "start_time": f"2026-08-11 09:{index:02d}:00",
            "end_time": f"2026-08-11 09:{index + 1:02d}:00",
            "normalized_title": f"GitHub issue {index}",
            "process_name": "chrome.exe",
            "category_key": "coding",
        }
        for index in range(10)
    ]

    section = _build_workflow_section(
        sessions,
        ["2026-08-05", "2026-08-11"],
        lambda process_name, _details: {"chrome.exe": "Chrome"}[process_name],
    )

    assert section["tools"] == ["Chrome"]
    assert section["tool_count"] == 1
    assert section["switch_count"] == 0


def test_workflow_counts_browser_to_codex_as_two_stable_tools():
    sessions = [
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:00:00",
            "end_time": "2026-08-11 09:10:00",
            "normalized_title": "GitHub",
            "process_name": "chrome.exe",
            "category_key": "coding",
        },
        {
            "date": "2026-08-11",
            "start_time": "2026-08-11 09:10:00",
            "end_time": "2026-08-11 09:20:00",
            "normalized_title": "project-a",
            "process_name": "Codex.exe",
            "category_key": "coding",
        },
    ]
    labels = {"chrome.exe": "Chrome", "Codex.exe": "Codex"}

    section = _build_workflow_section(
        sessions,
        ["2026-08-05", "2026-08-11"],
        lambda process_name, _details: labels[process_name],
    )

    assert section["tools"] == ["Chrome", "Codex"]
    assert section["tool_count"] == 2
    assert section["switch_count"] == 1


def test_interruption_rows_deduplicate_by_session_id_and_fallback_identity():
    work = {
        "session_id": "work",
        "date": "2026-08-11",
        "start_time": "2026-08-11 09:00:00",
        "end_time": "2026-08-11 09:20:00",
        "process_name": "Code.exe",
        "normalized_title": "Code",
        "category_key": "coding",
    }
    social = {
        "session_id": "social-a",
        "date": "2026-08-11",
        "start_time": "2026-08-11 09:25:00",
        "end_time": "2026-08-11 09:30:00",
        "process_name": "WeChat.exe",
        "normalized_title": "微信",
        "category_key": "social",
    }
    date_range = ["2026-08-05", "2026-08-11"]

    duplicate_id = _build_interruptions_section(
        [work, social, {**social, "normalized_title": "恢复副本"}],
        date_range,
        True,
    )
    distinct_ids = _build_interruptions_section(
        [work, social, {**social, "session_id": "social-b"}],
        date_range,
        True,
    )
    without_id = {**social, "session_id": ""}
    duplicate_fallback = _build_interruptions_section(
        [work, without_id, dict(without_id)],
        date_range,
        True,
    )

    assert duplicate_id["count"] == 1
    assert distinct_ids["count"] == 2
    assert duplicate_fallback["count"] == 1


def test_recovered_interruption_duplicates_do_not_reach_insight_threshold():
    work = {
        "session_id": "work",
        "date": "2026-08-11",
        "start_time": "2026-08-11 09:00:00",
        "end_time": "2026-08-11 09:20:00",
        "process_name": "Code.exe",
        "normalized_title": "Code",
        "category_key": "coding",
    }
    recovered = {
        "session_id": "social-recovered",
        "date": "2026-08-11",
        "start_time": "2026-08-11 09:25:00",
        "end_time": "2026-08-11 09:30:00",
        "process_name": "WeChat.exe",
        "normalized_title": "微信",
        "category_key": "social",
    }
    interruptions = _build_interruptions_section(
        [work, *[dict(recovered) for _ in range(8)]],
        ["2026-08-05", "2026-08-11"],
        True,
    )

    insight = select_primary_insight(
        {
            "date_range": ["2026-07-29", "2026-08-11"],
            "trust": {
                "level": "high",
                "reasons": [],
                "category_comparable": True,
            },
            "interruptions": interruptions,
        }
    )

    assert interruptions["count"] == 1
    assert insight is None


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


@pytest.mark.parametrize("failure_target", ["assess_range", "compare_ranges"])
def test_trusted_calculation_failure_hides_insight_without_calling_selector(
    tmp_path: Path,
    monkeypatch,
    caplog,
    failure_target,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    selector_calls = 0

    def fail_calculation(*_args, **_kwargs):
        raise RuntimeError(f"{failure_target} unavailable")

    def select_insight(_payload):
        nonlocal selector_calls
        selector_calls += 1
        return {"kind": "should-not-be-used"}

    monkeypatch.setattr(dashboard_service, failure_target, fail_calculation)
    monkeypatch.setattr(dashboard_service, "select_primary_insight", select_insight)

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert selector_calls == 0
    assert snapshot["insight"] is None
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["trust"]["reasons"] == ["统计数据格式异常"]
    assert snapshot["totals"]["effective_seconds"] == 0
    assert len(snapshot["trend"]["today"]) == 24
    assert "Failed to build trusted dashboard metrics" in caplog.text


def test_range_query_failure_preserves_old_snapshot_and_never_selects_insight(
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    selector_calls = 0

    def fail_range_query(*_args, **_kwargs):
        raise RuntimeError("range query unavailable")

    def select_insight(_payload):
        nonlocal selector_calls
        selector_calls += 1
        return {"kind": "should-not-be-used"}

    monkeypatch.setattr(
        dashboard_service.database,
        "query_date_range_stats",
        fail_range_query,
    )
    monkeypatch.setattr(dashboard_service, "select_primary_insight", select_insight)

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert selector_calls == 0
    assert snapshot["insight"] is None
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["totals"]["effective_seconds"] == 0
    assert snapshot["trend"]["thirty_days"] == []
    assert len(snapshot["trend"]["today"]) == 24
    assert "range query unavailable" in caplog.text


def test_thirty_day_trend_render_failure_keeps_trusted_insight(
    tmp_path: Path,
    monkeypatch,
    caplog,
):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()

    def fail_trend(_daily):
        raise RuntimeError("trend rendering unavailable")

    monkeypatch.setattr(
        dashboard_service,
        "_build_thirty_day_trend",
        fail_trend,
        raising=False,
    )

    snapshot = load_today_snapshot(
        str(db_path),
        lambda process_name, _details: process_name,
    )

    assert snapshot["trend"]["thirty_days"] == []
    assert snapshot["trust"]["level"] == "low"
    assert snapshot["insight"]["kind"] == "data_health"
    assert "trend rendering unavailable" in caplog.text


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
