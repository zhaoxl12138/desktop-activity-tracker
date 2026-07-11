from __future__ import annotations

import inspect
from datetime import datetime, timedelta

from daylens import database, exporter, timeline, utils
from daylens.gui import style as ui_style
from daylens.gui.pages.today_overview import TodayOverviewPage
from daylens.services import category_stats_service, dashboard_service
from daylens.session_tracker import ActivitySession


def test_dashboard_counts_office_as_work():
    stats = {
        "by_category": [
            {"category_key": "office", "effective_seconds": 600},
        ]
    }

    assert dashboard_service.category_seconds(stats)["work"] == 600


def test_work_detail_queries_office_category(monkeypatch):
    queried = []
    monkeypatch.setattr(
        category_stats_service.database,
        "query_category_detail",
        lambda _db, _date, key, _limit: queried.append(key) or [],
    )

    category_stats_service.load_category_detail("usage.db", "2026-07-11", "work")

    assert "office" in queried


def test_date_range_counts_office_as_work(tmp_path):
    db_path = tmp_path / "usage.db"
    now = datetime.now().replace(microsecond=0)
    conn = database.init_db(str(db_path))
    database.insert_session(
        conn,
        ActivitySession(
            session_id="office-session",
            start_time=now,
            end_time=now + timedelta(seconds=600),
            date=now.strftime("%Y-%m-%d"),
            process_name="excel.exe",
            exe_path="C:/excel.exe",
            window_title="Workbook",
            normalized_title="Workbook",
            category_key="office",
            category_name="办公套件",
            active_rule="interactive_required",
            duration_seconds=600,
            effective_seconds=600,
        ),
    )
    database.close_db(conn)

    result = database.query_date_range_stats(str(db_path), [now.strftime("%Y-%m-%d")])

    assert result["totals"]["work_seconds"] == 600


def test_exporter_has_no_legacy_work_category_literals():
    source = inspect.getsource(exporter)

    assert '{"ai_tools", "coding", "reading", "creative"}' not in source
    assert "('ai_tools','coding','reading','creative')" not in source


def test_office_is_a_work_category_in_shared_ui_and_timeline_rules():
    assert utils.normalize_category_bucket_key("office", "办公套件") == "work"
    assert "office" in timeline.WORK_CATS
    assert TodayOverviewPage._color_for_category(None, "office") == ui_style.COLORS["coding_green"]
    assert "office" in utils._DEFAULT_CATEGORIES
