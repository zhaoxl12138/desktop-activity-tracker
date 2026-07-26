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
