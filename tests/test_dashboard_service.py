from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database  # noqa: E402
from daylens.services.dashboard_service import (  # noqa: E402
    build_day_over_day_comparison,
    build_distribution_sections,
    build_hourly_series,
    build_top_app_rows,
    load_today_snapshot,
)


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


def test_today_snapshot_no_longer_exposes_insights(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()

    snapshot = load_today_snapshot(str(db_path), lambda process_name, details: process_name)

    assert "insights" not in snapshot
