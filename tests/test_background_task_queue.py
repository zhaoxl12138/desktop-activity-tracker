from __future__ import annotations

import os
import threading
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


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


def test_background_tasks_run_serially_and_deduplicate_keys():
    from daylens.gui.background_task_queue import BackgroundTaskQueue

    app = _app()
    first_started = threading.Event()
    release_first = threading.Event()
    lock = threading.Lock()
    running = 0
    max_running = 0
    completed = []

    def task(name, *, block=False):
        def run():
            nonlocal running, max_running
            with lock:
                running += 1
                max_running = max(max_running, running)
            try:
                if block:
                    first_started.set()
                    release_first.wait(timeout=2)
                return name
            finally:
                with lock:
                    running -= 1

        return run

    queue = BackgroundTaskQueue()
    queue.task_completed.connect(
        lambda key, result: completed.append((key, result))
    )

    assert queue.submit("report", task("first", block=True)) is True
    assert first_started.wait(timeout=1)
    assert queue.submit("scan", task("second")) is True
    assert queue.submit("scan", task("duplicate")) is False

    release_first.set()
    _wait_until(app, lambda: len(completed) == 2)

    assert completed == [("report", "first"), ("scan", "second")]
    assert max_running == 1
    assert queue.shutdown(timeout_ms=1_000) is True


def test_background_tasks_can_cancel_selected_pending_work():
    from daylens.gui.background_task_queue import BackgroundTaskQueue

    app = _app()
    first_started = threading.Event()
    release_first = threading.Event()
    completed = []
    cancelled = []

    def blocking_task():
        first_started.set()
        release_first.wait(timeout=2)
        return "first"

    queue = BackgroundTaskQueue()
    queue.task_completed.connect(
        lambda key, result: completed.append((key, result))
    )
    queue.task_cancelled.connect(cancelled.append)

    assert queue.submit("report", blocking_task) is True
    assert first_started.wait(timeout=1)
    assert queue.submit("scan", lambda: "scan") is True
    assert queue.submit("quality", lambda: "quality") is True

    assert queue.cancel_pending("scan") == ["scan"]
    release_first.set()
    _wait_until(app, lambda: len(completed) == 2)

    assert cancelled == ["scan"]
    assert completed == [("report", "first"), ("quality", "quality")]
    assert queue.shutdown(timeout_ms=1_000) is True


def test_background_task_queue_resumes_after_aborted_shutdown():
    from daylens.gui.background_task_queue import BackgroundTaskQueue

    app = _app()
    started = threading.Event()
    release = threading.Event()
    completed = []

    def blocking_task():
        started.set()
        release.wait(timeout=2)
        return "blocked"

    queue = BackgroundTaskQueue()
    queue.task_completed.connect(
        lambda key, result: completed.append((key, result))
    )
    assert queue.submit("running", blocking_task) is True
    assert started.wait(timeout=1)
    assert queue.submit("pending", lambda: "must not run") is True

    assert queue.shutdown(timeout_ms=1) is False
    assert queue.submit("rejected", lambda: "rejected") is False
    release.set()
    _wait_until(app, lambda: completed == [("running", "blocked")])

    queue.resume()
    assert queue.submit("resumed", lambda: "resumed") is True
    _wait_until(app, lambda: completed[-1:] == [("resumed", "resumed")])
    assert queue.shutdown(timeout_ms=1_000) is True
