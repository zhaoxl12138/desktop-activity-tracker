"""Foreground shell surfaces are idle; ordinary Explorer folders are not."""

from __future__ import annotations

from dataclasses import replace

import pytest

from daylens import window_detector
from daylens.session_tracker import SessionTracker


class _Classifier:
    def classify(self, process_name, title):
        if process_name.lower() == "explorer.exe":
            return {
                "category_key": "tools",
                "category_name": "系统工具",
                "active_rule": "interactive_required",
            }
        if process_name == "Code.exe":
            return {
                "category_key": "coding",
                "category_name": "编程开发",
                "active_rule": "interactive_required",
            }
        raise AssertionError(f"Unexpected classification: {process_name} {title}")


@pytest.fixture(autouse=True)
def stable_input(monkeypatch):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot", lambda: bytes(256)
    )


def _tracker(*, on_session_end=None, cross_group_grace=30):
    return SessionTracker(
        config={"tracker": {
            "sample_interval_seconds": 1,
            "idle_threshold_seconds": 60,
            "cross_group_grace_seconds": cross_group_grace,
            "min_session_seconds": 1,
        }},
        classifier=_Classifier(),
        on_session_end=on_session_end,
    )


def _window(window_class, title="", process_name="explorer.exe"):
    return {
        "hwnd": 42,
        "window_title": title,
        "window_class": window_class,
        "process_name": process_name,
        "exe_path": r"C:\Windows\explorer.exe",
        "pid": 15,
    }


@pytest.mark.parametrize("window_class", [
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"
])
def test_shell_desktop_predicate_only_matches_explorer_shell_classes(window_class):
    assert window_detector.is_shell_desktop_window("explorer.exe", window_class)
    assert not window_detector.is_shell_desktop_window("Code.exe", window_class)
    assert not window_detector.is_shell_desktop_window("explorer.exe", "CabinetWClass")
    assert not window_detector.is_shell_desktop_window("explorer.exe", "ExploreWClass")


def test_window_detector_captures_class_without_dropping_window(monkeypatch):
    monkeypatch.setattr(window_detector.win32gui, "GetForegroundWindow", lambda: 42)
    monkeypatch.setattr(window_detector.win32gui, "GetWindowText", lambda _: "")
    monkeypatch.setattr(window_detector.win32gui, "GetClassName", lambda _: "Progman")
    monkeypatch.setattr(
        window_detector.win32process, "GetWindowThreadProcessId", lambda _: (1, 15)
    )

    class _Process:
        def __init__(self, pid):
            assert pid == 15

        def name(self):
            return "explorer.exe"

        def exe(self):
            return r"C:\Windows\explorer.exe"

    monkeypatch.setattr(window_detector.psutil, "Process", _Process)
    observation = window_detector.get_foreground_window_info()
    assert observation["window_class"] == "Progman"
    assert observation["process_name"] == "explorer.exe"

    def failed_class(_):
        raise RuntimeError("class unavailable")

    monkeypatch.setattr(window_detector.win32gui, "GetClassName", failed_class)
    observation = window_detector.get_foreground_window_info()
    assert observation["process_name"] == "explorer.exe"
    assert observation["window_class"] == ""


@pytest.mark.parametrize("window_class", [
    "Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"
])
def test_active_mouse_on_shell_desktop_is_idle_from_first_sample(window_class):
    tracker = _tracker()
    tracker.mark_user_active()
    snapshot = tracker.tick(0, _window(window_class))
    current = tracker.current_session

    assert current.category_key == "idle"
    assert current.idle_seconds == 1
    assert current.engaged_seconds == current.passive_seconds == current.effective_seconds == 0
    assert current.duration_seconds == 1
    assert snapshot["attention_state"] == "idle"
    assert snapshot["is_user_active"] is False


def test_no_foreground_window_is_idle_immediately_even_after_input():
    tracker = _tracker()
    tracker.mark_user_active()
    snapshot = tracker.tick(0, None)
    current = tracker.current_session
    assert current.category_key == "idle"
    assert current.idle_seconds == current.duration_seconds == 1
    assert current.effective_seconds == 0
    assert snapshot["attention_state"] == "idle"
    assert snapshot["is_user_active"] is False


def test_file_explorer_folder_window_remains_effective_when_active():
    tracker = _tracker()
    tracker.mark_user_active()
    tracker.tick(0, _window("CabinetWClass", title="Documents"))
    current = tracker.current_session
    assert current.category_key == "tools"
    assert current.engaged_seconds == current.effective_seconds == 1
    assert current.idle_seconds == 0


def test_desktop_grace_does_not_increase_prior_work_effective_time():
    tracker = _tracker(cross_group_grace=30)
    code = _window("CodeWindow", title="main.py", process_name="Code.exe")
    tracker.mark_user_active()
    tracker.tick(0, code)
    prior_effective = tracker.current_session.effective_seconds

    tracker.mark_user_active()
    tracker.tick(0, _window("Progman"))
    tracker.mark_user_active()
    tracker.tick(0, _window("Progman"))

    assert tracker.current_session.effective_seconds == prior_effective
    assert tracker._pending_switch["idle_during_grace"] == 2
    assert tracker._pending_switch["engaged_during_grace"] == 0


def test_completed_desktop_switch_preserves_previous_work_session():
    ended = []
    tracker = _tracker(on_session_end=lambda row: ended.append(replace(row)), cross_group_grace=0)
    code = _window("CodeWindow", title="main.py", process_name="Code.exe")
    tracker.mark_user_active()
    tracker.tick(0, code)
    tracker.tick(0, _window("Progman"))
    tracker.tick(0, _window("Progman"))

    assert len(ended) == 1
    assert ended[0].category_key == "coding"
    assert ended[0].effective_seconds == ended[0].engaged_seconds == 1
    assert ended[0].idle_seconds == 0
    assert tracker.current_session.category_key == "idle"
    assert tracker.current_session.effective_seconds == 0
    assert tracker.current_session.idle_seconds == tracker.current_session.duration_seconds == 2
