from daylens.services.dashboard_history_cache import DashboardHistoryCache

import sqlite3
from datetime import datetime

import pytest

from daylens import database


def _history_database(tmp_path):
    path = str(tmp_path / "usage.db")
    conn = database.init_db(path)
    conn.execute("""INSERT INTO activity_sessions (
        session_id,start_time,end_time,date,process_name,normalized_title,
        category_key,category_name,active_rule,duration_seconds,effective_seconds,
        engaged_seconds,passive_seconds,idle_seconds,metric_version,classification_version)
        VALUES ('s','2026-10-28 09:00:00','2026-10-28 09:10:00','2026-10-28',
        'game.exe','Game','gaming','游戏娱乐','interactive_required',600,600,600,0,0,
        'attention-v1','manual-correction-v1')""")
    conn.commit()
    conn.close()
    return path


@pytest.mark.parametrize("change", [
    "category_key='reading',category_name='阅读学习'",
    "effective_seconds=500,engaged_seconds=500,idle_seconds=100",
    "normalized_title='Different activity'",
    "start_time='2026-10-28 08:59:00'",
    "classification_source='manual'",
])
def test_history_revision_covers_content_changes_without_version_changes(tmp_path, change):
    db = _history_database(tmp_path)
    before = database.query_completed_history_revision(db, "2026-10-28", "2026-10-28")
    conn = sqlite3.connect(db)
    conn.execute("UPDATE activity_sessions SET " + change)
    conn.commit()
    conn.close()
    assert database.query_completed_history_revision(db, "2026-10-28", "2026-10-28") != before


def test_history_revision_ignores_rows_outside_the_requested_dates(tmp_path):
    db = _history_database(tmp_path)
    before = database.query_completed_history_revision(db, "2026-10-28", "2026-10-28")
    conn = sqlite3.connect(db)
    conn.execute("""INSERT INTO activity_logs (timestamp,date,duration_seconds)
                    VALUES ('2026-10-29 10:00:00','2026-10-29',10)""")
    conn.commit()
    conn.close()
    assert database.query_completed_history_revision(db, "2026-10-28", "2026-10-28") == before


def test_dashboard_refresh_sees_repeated_category_correction(tmp_path, monkeypatch):
    from daylens.services import dashboard_service

    class Today(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 29, 12)

    monkeypatch.setattr(dashboard_service, "datetime", Today)
    db = _history_database(tmp_path)
    first = dashboard_service.load_today_snapshot(db, lambda process, _: process)
    conn = sqlite3.connect(db)
    conn.execute("UPDATE activity_sessions SET category_key='reading',category_name='阅读学习'")
    conn.commit()
    conn.close()
    second = dashboard_service.load_today_snapshot(db, lambda process, _: process)
    assert first["entertainment_history"]["week"]["summary"]["total_seconds"] == 600
    assert second["entertainment_history"]["week"]["summary"]["total_seconds"] == 0


def test_dashboard_does_not_cache_new_content_under_old_revision(tmp_path, monkeypatch):
    from daylens.services import dashboard_service

    class Today(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 29, 12)

    monkeypatch.setattr(dashboard_service, "datetime", Today)
    db = _history_database(tmp_path)
    original_revision = database.query_completed_history_revision

    def edit(category, name):
        conn = sqlite3.connect(db)
        conn.execute("UPDATE activity_sessions SET category_key=?, category_name=?", (category, name))
        conn.commit()
        conn.close()

    def revision_then_edit(*args):
        revision = original_revision(*args)
        monkeypatch.setattr(database, "query_completed_history_revision", original_revision)
        edit("reading", "阅读学习")
        return revision

    monkeypatch.setattr(database, "query_completed_history_revision", revision_then_edit)
    first = dashboard_service.load_today_snapshot(db, lambda p, _: p)
    second = dashboard_service.load_today_snapshot(db, lambda p, _: p)
    edit("gaming", "游戏娱乐")
    restored = dashboard_service.load_today_snapshot(db, lambda p, _: p)
    assert [s["entertainment_history"]["week"]["summary"]["total_seconds"]
            for s in (first, second, restored)] == [600, 0, 600]


def test_completed_history_cache_ignores_live_today_changes():
    cache = DashboardHistoryCache()
    calls = []
    revision = (10, 99, "attention-v1", "rules-v2")

    def load():
        calls.append("load")
        return {"daily": [{"date": "2026-10-20"}]}, [{"session_id": "old"}], {"totals": {}}

    first = cache.get_or_load(
        db_path="usage.db",
        dates=["2026-10-01", "2026-10-20"],
        revision=revision,
        loader=load,
    )
    second = cache.get_or_load(
        db_path="usage.db",
        dates=["2026-10-01", "2026-10-20"],
        revision=revision,
        loader=load,
    )

    assert first is second
    assert calls == ["load"]


def test_completed_history_cache_invalidates_on_metric_or_classification_revision():
    cache = DashboardHistoryCache()
    calls = 0

    def load():
        nonlocal calls
        calls += 1
        return {"daily": []}, [], {"totals": {}}

    for revision in (
        (10, 99, "attention-v1", "rules-v1"),
        (10, 99, "attention-v2", "rules-v1"),
        (10, 99, "attention-v2", "rules-v2"),
    ):
        cache.get_or_load(
            db_path="usage.db",
            dates=["2026-10-01", "2026-10-20"],
            revision=revision,
            loader=load,
        )

    assert calls == 3


def test_completed_history_cache_is_bounded():
    cache = DashboardHistoryCache(max_entries=2)
    for index in range(3):
        cache.get_or_load(
            db_path=f"usage-{index}.db",
            dates=["2026-10-20"],
            revision=(index,),
            loader=lambda: ({"daily": []}, [], {"totals": {}}),
        )

    assert cache.size == 2
