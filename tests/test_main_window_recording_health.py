from datetime import datetime
from types import SimpleNamespace

from daylens.gui.main_window import MainWindow


class Label:
    def __init__(self):
        self.text = ""
        self.style = ""

    def setText(self, value):
        self.text = value

    def setStyleSheet(self, value):
        self.style = value


def test_recording_health_ui_uses_real_sample_time_and_does_not_invent_one():
    window = SimpleNamespace(
        sidebar_record_status=Label(),
        sidebar_sample_time=Label(),
        _recording_health=None,
    )
    window._update_recording_health_ui = lambda: (
        MainWindow._update_recording_health_ui(window)
    )
    stopped = SimpleNamespace(
        status="stopped",
        last_sample_at=datetime(2026, 7, 26, 9, 15, 30),
        error="",
        recovery_status="none",
    )

    MainWindow._on_recording_health(window, stopped)

    assert window.sidebar_sample_time.text.endswith("09:15:30")
    assert "stopped" in window.sidebar_record_status.text.lower()

    MainWindow._update_recording_health_ui(window)
    assert window.sidebar_sample_time.text.endswith("09:15:30")


def test_recording_health_ui_exposes_delay_and_error_without_sample_time():
    window = SimpleNamespace(
        sidebar_record_status=Label(),
        sidebar_sample_time=Label(),
        _recording_health=None,
    )
    window._update_recording_health_ui = lambda: (
        MainWindow._update_recording_health_ui(window)
    )
    delayed = SimpleNamespace(
        status="sample_delayed",
        last_sample_at=None,
        error="foreground unavailable",
        recovery_status="none",
    )

    MainWindow._on_recording_health(window, delayed)

    assert "delayed" in window.sidebar_record_status.text.lower()
    assert window.sidebar_sample_time.text.endswith("--")
    assert "foreground unavailable" in window.sidebar_record_status.text
