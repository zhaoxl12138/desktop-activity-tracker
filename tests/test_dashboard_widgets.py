from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker.gui.widgets.dashboard_widgets import TimelineWidget  # noqa: E402


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def test_timeline_widget_expand_and_collapse():
    app = _app()
    widget = TimelineWidget(max_rows=2)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:25:00",
            "process_name": "Code.exe",
            "category_name": "学习/工作",
            "category_key": "coding",
            "effective_seconds": 1500,
        },
        {
            "start_time": "2026-06-02 09:30:00",
            "end_time": "2026-06-02 09:45:00",
            "process_name": "WeChat.exe",
            "category_name": "社交通讯",
            "category_key": "social",
            "effective_seconds": 900,
        },
        {
            "start_time": "2026-06-02 10:00:00",
            "end_time": "2026-06-02 10:40:00",
            "process_name": "chrome.exe",
            "category_name": "视频娱乐",
            "category_key": "video",
            "effective_seconds": 2400,
        },
    ]

    widget.set_sessions(sessions, {"Code.exe": "VS Code", "WeChat.exe": "微信"})
    widget.show()
    app.processEvents()

    assert len(widget._rows) == 2
    assert widget.more_label.text() == "查看更多 ↓"
    assert widget.more_label.isEnabled() is True

    widget.more_label.click()
    app.processEvents()

    assert len(widget._rows) == 3
    assert widget.more_label.text() == "收起 ↑"

    widget.more_label.click()
    app.processEvents()

    assert len(widget._rows) == 2
    assert widget.more_label.text() == "查看更多 ↓"


def test_timeline_widget_hides_expand_behavior_for_short_lists():
    app = _app()
    widget = TimelineWidget(max_rows=3)
    sessions = [
        {
            "start_time": "2026-06-02 09:00:00",
            "end_time": "2026-06-02 09:10:00",
            "process_name": "Code.exe",
            "category_name": "学习/工作",
            "category_key": "coding",
            "effective_seconds": 600,
        }
    ]

    widget.set_sessions(sessions)
    widget.show()
    app.processEvents()

    assert len(widget._rows) == 1
    assert widget.more_label.text() == "查看更多 ↓"
    assert widget.more_label.isEnabled() is False
