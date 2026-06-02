from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database, timeline  # noqa: E402
from daylens.gui.pages.live_monitor import LiveMonitorPage  # noqa: E402
from daylens.session_tracker import ActivitySession  # noqa: E402


def _insert_session(
    conn,
    *,
    process_name: str,
    effective_seconds: int,
    category_key: str = "coding",
    start_offset_seconds: int = 0,
) -> None:
    start = datetime.now().replace(microsecond=0) + timedelta(seconds=start_offset_seconds)
    duration = max(effective_seconds, 1)
    database.insert_session(
        conn,
        ActivitySession(
            session_id=uuid.uuid4().hex[:12],
            start_time=start,
            end_time=start + timedelta(seconds=duration),
            date=start.strftime("%Y-%m-%d"),
            process_name=process_name,
            exe_path="",
            window_title=process_name.removesuffix(".exe"),
            normalized_title=process_name.removesuffix(".exe"),
            category_key=category_key,
            category_name="编程开发",
            active_rule="interactive_required",
            duration_seconds=duration,
            effective_seconds=effective_seconds,
            idle_seconds=0,
            switch_reason="test",
        ),
    )


def test_daylens_sessions_are_excluded_from_date_stats_totals(tmp_path):
    db_path = os.path.join(tmp_path, "usage.db")
    conn = database.init_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    _insert_session(conn, process_name="DayLens.exe", effective_seconds=300)
    _insert_session(conn, process_name="Code.exe", effective_seconds=120)
    database.close_db(conn)

    stats = database.query_date_stats(db_path, today)

    assert stats["totals"]["effective_seconds"] == 120
    assert stats["totals"]["total_seconds"] == 120
    assert stats["by_category"][0]["effective_seconds"] == 120
    assert [item["process_name"] for item in stats["by_app"]] == ["Code.exe"]


def test_daylens_sessions_are_excluded_from_date_range_and_switch_count(tmp_path):
    db_path = os.path.join(tmp_path, "usage.db")
    conn = database.init_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    _insert_session(conn, process_name="DayLens.exe", effective_seconds=300)
    _insert_session(conn, process_name="Code.exe", effective_seconds=120, start_offset_seconds=120)
    database.close_db(conn)

    stats = database.query_date_range_stats(db_path, [today])

    assert stats["daily"][0]["effective_seconds"] == 120
    assert stats["totals"]["effective_seconds"] == 120
    assert stats["by_app"][0]["process_name"] == "Code.exe"
    assert database.query_session_count(db_path, today) == 1


def test_daylens_sessions_are_excluded_from_timeline(tmp_path):
    db_path = os.path.join(tmp_path, "usage.db")
    conn = database.init_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    _insert_session(conn, process_name="DayLens.exe", effective_seconds=300)
    database.close_db(conn)

    blocks = timeline.build_timeline(db_path, today)

    assert sum(block.effective_seconds for block in blocks) == 0
    assert all(block.top_app != "DayLens.exe" for block in blocks)


def test_live_monitor_does_not_add_ignored_daylens_samples_to_history():
    app = QApplication.instance() or QApplication([])
    page = LiveMonitorPage()

    page.on_sample_updated(
        {
            "timestamp": "2026-06-02 17:30:37",
            "process_name": "DayLens.exe",
            "window_title": "DayLens",
            "normalized_title": "DayLens",
            "category_key": "tools",
            "category_name": "系统工具",
            "duration_seconds": 0,
            "effective_seconds": 0,
            "session_idle_seconds": 0,
            "idle_seconds": 0,
            "is_effective": False,
            "is_ignored": True,
        }
    )

    assert page.table.rowCount() == 0
    assert page.lbl_process.text() == "DayLens.exe"
    page.deleteLater()
    app.processEvents()
