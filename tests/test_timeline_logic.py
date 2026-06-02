from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database  # noqa: E402
from daylens import classifier  # noqa: E402
from daylens.gui.widgets.dashboard_widgets import _timeline_duration_text  # noqa: E402
from daylens.session_tracker import ActivitySession, SessionTracker, normalize_window_title  # noqa: E402


class FakeClassifier:
    def classify(self, process_name, window_title):
        return {
            "category_key": "coding",
            "category_name": "编程开发",
            "active_rule": "interactive_required",
        }


def test_timeline_duration_keeps_seconds_precision():
    text = _timeline_duration_text({"duration_seconds": 5, "effective_seconds": 5})

    assert text == "5秒"


def test_timeline_duration_uses_idle_when_effective_is_zero():
    text = _timeline_duration_text(
        {"duration_seconds": 12, "effective_seconds": 0, "idle_seconds": 12}
    )

    assert text == "12秒"


def test_today_sessions_include_idle_only_sessions(tmp_path):
    db_path = os.path.join(tmp_path, "usage.db")
    conn = database.init_db(db_path)
    today = datetime.now().strftime("%Y-%m-%d")
    session = ActivitySession(
        session_id=uuid.uuid4().hex[:12],
        start_time=datetime.now(),
        end_time=datetime.now(),
        date=today,
        process_name="explorer.exe",
        exe_path="",
        window_title="Program Manager",
        normalized_title="Program Manager",
        category_key="tools",
        category_name="系统工具",
        active_rule="interactive_required",
        duration_seconds=12,
        effective_seconds=0,
        idle_seconds=12,
        switch_reason="test",
    )
    database.insert_session(conn, session)
    conn.close()

    sessions = database.query_today_sessions(db_path, today)

    assert len(sessions) == 1
    assert sessions[0]["idle_seconds"] == 12


def test_dynamic_terminal_title_prefixes_are_normalized():
    assert normalize_window_title("WindowsTerminal.exe", "✳ auto-scan-classify") == "auto-scan-classify"
    assert normalize_window_title("WindowsTerminal.exe", "⠐ auto-scan-classify") == "auto-scan-classify"


def test_finish_current_closes_session_without_replacement():
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 99, "min_session_seconds": 1}},
        classifier=FakeClassifier(),
        on_session_end=lambda session: ended.append(session),
    )
    tracker.tick(0.5, {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""})

    tracker.finish_current("ignored_process")

    assert tracker.current_session is None
    assert len(ended) == 1
    assert ended[0].switch_reason == "ignored_process"


def test_worker_self_window_snapshot_is_marked_ignored():
    clf = classifier.Classifier("config/config.yaml")
    result = clf.classify("DayLens.exe", "DayLens")
    assert result["category_key"] == "tools", (
        f"DayLens should be classified as tools, got {result['category_key']}"
    )
