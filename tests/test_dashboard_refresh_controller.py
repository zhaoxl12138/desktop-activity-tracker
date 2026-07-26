from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from daylens.gui.dashboard_refresh_controller import DashboardRefreshController


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _wait_until(app: QApplication, predicate, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    app.processEvents()
    assert predicate()


def test_refresh_controller_is_single_flight_and_discards_stale_results():
    app = _app()
    release_first = threading.Event()
    first_started = threading.Event()
    lock = threading.Lock()
    calls = 0
    running = 0
    max_running = 0

    def load_snapshot():
        nonlocal calls, running, max_running
        with lock:
            calls += 1
            call_number = calls
            running += 1
            max_running = max(max_running, running)
        try:
            if call_number == 1:
                first_started.set()
                release_first.wait(timeout=2)
            return {"call": call_number}
        finally:
            with lock:
                running -= 1

    controller = DashboardRefreshController(load_snapshot, interval_ms=60_000)
    received = []
    controller.snapshot_ready.connect(received.append)

    controller.set_foreground(True)
    assert first_started.wait(timeout=1)
    controller.request_refresh()
    release_first.set()

    _wait_until(app, lambda: len(received) == 1)

    assert calls == 2
    assert max_running == 1
    assert received[0].payload == {"call": 2}
    assert received[0].generation == controller.latest_generation
    assert controller.shutdown(timeout_ms=1_000) is True


def test_refresh_controller_pauses_hidden_window_and_refreshes_on_restore():
    app = _app()
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        return {"call": calls}

    controller = DashboardRefreshController(load_snapshot, interval_ms=20)
    controller.set_foreground(True)
    _wait_until(app, lambda: calls >= 1)
    controller.set_foreground(False)
    hidden_calls = calls

    deadline = time.monotonic() + 0.08
    while time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)

    assert controller.timer.isActive() is False
    assert calls == hidden_calls

    controller.set_foreground(True)
    _wait_until(app, lambda: calls > hidden_calls)
    assert controller.shutdown(timeout_ms=1_000) is True


def test_refresh_controller_can_resume_when_exit_wait_times_out():
    app = _app()
    release = threading.Event()
    calls = 0

    def load_snapshot():
        nonlocal calls
        calls += 1
        if calls == 1:
            release.wait(timeout=2)
        return {"call": calls}

    controller = DashboardRefreshController(load_snapshot, interval_ms=60_000)
    received = []
    controller.snapshot_ready.connect(received.append)
    controller.set_foreground(True)
    _wait_until(app, lambda: calls == 1)

    assert controller.shutdown(timeout_ms=1) is False
    controller.resume(True)
    release.set()

    _wait_until(app, lambda: len(received) == 1)
    assert received[0].payload == {"call": 2}
    assert controller.shutdown(timeout_ms=1_000) is True
