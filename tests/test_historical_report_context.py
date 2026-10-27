from __future__ import annotations

from daylens import exporter


def test_historical_daily_suggestions_end_trend_at_report_date(monkeypatch):
    requested_dates = []
    monkeypatch.setattr(
        exporter.database,
        "query_date_range_stats",
        lambda _db_path, dates: requested_dates.append(dates)
        or {
            "daily": [
                {"video_seconds": 5_500},
                {"video_seconds": 5_500},
                {"video_seconds": 5_500},
            ]
        },
    )
    stats = {
        "totals": {
            "effective_seconds": 10_800,
            "idle_seconds": 0,
        },
        "by_category": [
            {
                "category_key": "video",
                "effective_seconds": 5_500,
            }
        ],
    }

    suggestions, _work, _video = exporter._generate_suggestions(
        "usage.db",
        "2026-07-12",
        stats,
    )

    assert requested_dates == [
        ["2026-07-10", "2026-07-11", "2026-07-12"]
    ]
    assert "娱乐休闲时间连续3天超过90分钟，建议减少视频时间" in suggestions


def test_daily_suggestions_use_shared_aggregate_category_keys(monkeypatch):
    monkeypatch.setattr(
        exporter.database,
        "query_date_range_stats",
        lambda _db_path, _dates: {"daily": []},
    )
    stats = {
        "totals": {"effective_seconds": 10_800, "idle_seconds": 0},
        "by_category": [
            {"category_key": "work", "effective_seconds": 7_200},
            {"category_key": "entertainment", "effective_seconds": 3_600},
        ],
    }

    suggestions, work_seconds, entertainment_seconds = exporter._generate_suggestions(
        "usage.db", "2026-10-27", stats,
    )

    assert work_seconds == 7_200
    assert entertainment_seconds == 3_600
    assert not any("工作学习占比较低" in item for item in suggestions)
