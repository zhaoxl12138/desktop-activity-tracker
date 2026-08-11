from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens import database  # noqa: E402
from daylens import classifier  # noqa: E402
from daylens.gui.pages.today_overview import TodayOverviewPage  # noqa: E402
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


def test_focus_axis_includes_the_last_minute_of_the_day():
    class AxisContext:
        @staticmethod
        def _to_minute(timestamp):
            return TodayOverviewPage._to_minute(None, timestamp)

        @staticmethod
        def _color_for_category(_key, _name=""):
            return "active"

    colors = TodayOverviewPage._build_focus_axis(
        AxisContext(),
        [
            {
                "start_time": "2026-07-26 23:59:00",
                "end_time": "2026-07-26 23:59:59",
                "effective_seconds": 59,
                "idle_seconds": 0,
                "category_key": "coding",
            }
        ],
    )

    assert len(colors) == 1440
    assert colors[1439] == "active"


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


def test_switching_apps_creates_separate_sessions_even_in_same_domain(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr("daylens.session_tracker._get_keyboard_snapshot", lambda: b"")
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 99, "min_session_seconds": 1}},
        classifier=FakeClassifier(),
        on_session_end=ended.append,
    )
    tracker.tick(0, {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""})
    first_id = tracker.current_session.session_id
    tracker.tick(0, {"process_name": "Obsidian.exe", "window_title": "notes", "exe_path": ""})

    assert tracker.current_session.session_id != first_id
    assert ended and ended[0].process_name == "Code.exe"


def test_grace_period_time_is_not_counted_twice(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr("daylens.session_tracker._get_keyboard_snapshot", lambda: b"")
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 99, "min_session_seconds": 1}},
        classifier=FakeClassifier(),
    )
    tracker.tick(0, {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""})
    before = tracker.current_session.duration_seconds
    tracker._pending_switch = {
        "domain": "entertainment",
        "since": datetime.now(),
        "cat_key": "video",
        "active_rule": "passive_allowed",
        "engaged_during_grace": 0,
        "passive_during_grace": 0,
        "idle_during_grace": 0,
        "idle_corrected": False,
    }
    tracker._tick_grace_current(datetime.now())

    assert tracker.current_session.duration_seconds == before


def test_video_auto_close_keeps_duration_components_consistent(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr("daylens.session_tracker._get_keyboard_snapshot", lambda: b"")
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 999, "min_session_seconds": 1, "entertainment_idle_threshold_seconds": 3}},
        classifier=FakeClassifier(), on_session_end=ended.append,
    )
    tracker._current = ActivitySession(
        session_id="video", start_time=datetime.now(), end_time=datetime.now(), date=datetime.now().strftime("%Y-%m-%d"),
        process_name="vlc.exe", exe_path="", window_title="Movie", normalized_title="Movie", category_key="video",
        category_name="video", active_rule="passive_allowed", initial_title="Movie",
        duration_seconds=10, effective_seconds=10, engaged_seconds=10,
    )
    tracker.idle_threshold = 1
    for _ in range(4):
        tracker._tick_current(10, datetime.now())

    assert ended
    session = ended[0]
    assert session.duration_seconds == (
        session.engaged_seconds + session.passive_seconds + session.idle_seconds
    )
    assert session.effective_seconds == (
        session.engaged_seconds + session.passive_seconds
    )


def test_large_sampling_gap_closes_session(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr("daylens.session_tracker._get_keyboard_snapshot", lambda: b"")
    ended = []
    tracker = SessionTracker(
        config={"tracker": {"sample_interval_seconds": 1, "flush_interval_seconds": 99, "min_session_seconds": 1}},
        classifier=FakeClassifier(), on_session_end=ended.append,
    )
    tracker.tick(0, {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""})
    tracker._last_tick_wall_time -= timedelta(seconds=600)
    tracker.tick(0, {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""})

    assert ended and ended[0].switch_reason == "system_gap"
    assert ended[0].duration_seconds == (
        ended[0].engaged_seconds
        + ended[0].passive_seconds
        + ended[0].idle_seconds
    )
    assert ended[0].effective_seconds == (
        ended[0].engaged_seconds + ended[0].passive_seconds
    )


def test_cross_day_boundary_preserves_attention_counters(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr("daylens.session_tracker._get_keyboard_snapshot", lambda: b"")
    ended = []
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": 1,
                "flush_interval_seconds": 99,
                "min_session_seconds": 1,
            }
        },
        classifier=FakeClassifier(),
        on_session_end=ended.append,
    )
    window = {"process_name": "Code.exe", "window_title": "main.py", "exe_path": ""}
    tracker.mark_user_active()
    tracker.tick(0, window)
    tracker.current_session.date = "1999-01-01"

    tracker.tick(0, window)

    assert ended and ended[0].switch_reason == "cross_day"
    assert ended[0].duration_seconds == (
        ended[0].engaged_seconds
        + ended[0].passive_seconds
        + ended[0].idle_seconds
    )
    assert ended[0].effective_seconds == (
        ended[0].engaged_seconds + ended[0].passive_seconds
    )


def test_worker_self_window_snapshot_is_marked_ignored():
    clf = classifier.Classifier("config/config.yaml")
    result = clf.classify("DayLens.exe", "DayLens")
    assert result["category_key"] == "tools", (
        f"DayLens should be classified as tools, got {result['category_key']}"
    )
