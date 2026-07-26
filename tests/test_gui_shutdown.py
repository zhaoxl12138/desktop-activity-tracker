from __future__ import annotations

from types import SimpleNamespace

from PySide6.QtWidgets import QMessageBox

from daylens.gui import main_window, tray_manager
from daylens.gui.main_window import MainWindow
from daylens.gui.tray_manager import TrayManager
from daylens.services import gui_bootstrap
from daylens.services.gui_shutdown_service import (
    WorkerShutdownResult,
    stop_recording_worker_safely,
)


class FakeWorker:
    def __init__(self, *, wait_result: bool, budget_ms: int = 42_000):
        self.wait_result = wait_result
        self.budget_ms = budget_ms
        self.calls: list[object] = []

    def shutdown_wait_budget_ms(self) -> int:
        self.calls.append("budget")
        return self.budget_ms

    def stop(self) -> None:
        self.calls.append("stop")

    def wait(self, timeout_ms: int) -> bool:
        self.calls.append(("wait", timeout_ms))
        return self.wait_result


def test_safe_shutdown_uses_worker_cleanup_budget_and_checks_wait_result():
    worker = FakeWorker(wait_result=True)

    result = stop_recording_worker_safely(worker)

    assert result.completed is True
    assert result.timeout_ms == 15_000
    assert worker.calls == ["budget", "stop", ("wait", 15_000)]


def test_safe_shutdown_timeout_returns_actionable_failure_and_keeps_worker():
    worker = FakeWorker(wait_result=False)

    result = stop_recording_worker_safely(worker)

    assert result.completed is False
    assert result.worker is worker
    assert "retry" in result.message.lower()
    assert "not" in result.message.lower()
    assert worker.calls == ["budget", "stop", ("wait", 15_000)]


def test_safe_shutdown_rejects_joined_worker_with_fatal_health():
    worker = FakeWorker(wait_result=True)
    worker.health = SimpleNamespace(
        status="fatal",
        pending_persists=0,
        recovery_path=r"D:\Data\usage.db.session-recovery.json",
        recovery_status="failed",
    )

    result = stop_recording_worker_safely(worker)

    assert result.completed is False
    assert "fatal" in result.message
    assert "session-recovery.json" in result.message


def test_safe_shutdown_rejects_joined_worker_with_volatile_pending_sessions():
    worker = FakeWorker(wait_result=True)
    worker.health = SimpleNamespace(
        status="stopped",
        pending_persists=2,
        recovery_path=r"D:\Data\usage.db.session-recovery.json",
        recovery_status="failed",
    )

    result = stop_recording_worker_safely(worker)

    assert result.completed is False
    assert "2" in result.message
    assert "failed" in result.message


def test_main_window_quit_timeout_does_not_quit_or_discard_worker(monkeypatch):
    worker = FakeWorker(wait_result=False)
    window = SimpleNamespace(worker=worker)
    events: list[str] = []
    warnings: list[str] = []
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        lambda candidate: WorkerShutdownResult(
            completed=False,
            worker=candidate,
            timeout_ms=42_000,
            message="Still cleaning; retry later.",
        ),
    )
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes)
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )
    monkeypatch.setattr(
        main_window.QApplication,
        "instance",
        staticmethod(lambda: SimpleNamespace(quit=lambda: events.append("quit"))),
    )

    MainWindow._quit_app(window)

    assert events == []
    assert warnings == ["Still cleaning; retry later."]
    assert window.worker is worker


def test_main_window_restart_schedule_failure_does_not_stop_worker(monkeypatch):
    worker = FakeWorker(wait_result=True)
    window = SimpleNamespace(worker=worker)
    shutdown_calls = []
    warnings = []
    monkeypatch.setattr(main_window, "current_launch_command", lambda: ["daylens"])
    monkeypatch.setattr(
        main_window,
        "schedule_restart",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("waiter unavailable")
        ),
    )
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        shutdown_calls.append,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    MainWindow._restart_app(window)

    assert shutdown_calls == []
    assert warnings == ["waiter unavailable"]
    assert worker.calls == []


def test_main_window_restart_shutdown_failure_cancels_waiter(monkeypatch):
    worker = FakeWorker(wait_result=False)
    window = SimpleNamespace(worker=worker)
    events = []
    handle = SimpleNamespace(
        arm=lambda: events.append("arm"),
        cancel=lambda: events.append("cancel"),
    )
    monkeypatch.setattr(main_window, "current_launch_command", lambda: ["daylens"])
    monkeypatch.setattr(
        main_window,
        "schedule_restart",
        lambda command, deferred: events.append(("schedule", command, deferred))
        or handle,
    )
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        lambda candidate: events.append(("stop", candidate))
        or WorkerShutdownResult(
            completed=False,
            worker=candidate,
            timeout_ms=12_000,
            message="recovery pending",
        ),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    MainWindow._restart_app(window)

    assert events == [
        ("schedule", ["daylens"], True),
        ("stop", worker),
        "cancel",
    ]


def test_main_window_restart_command_failure_does_not_stop_worker(monkeypatch):
    worker = FakeWorker(wait_result=True)
    window = SimpleNamespace(worker=worker)
    shutdown_calls = []
    warnings = []
    monkeypatch.setattr(
        main_window,
        "current_launch_command",
        lambda: (_ for _ in ()).throw(OSError("command unavailable")),
    )
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        shutdown_calls.append,
    )
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    MainWindow._restart_app(window)

    assert shutdown_calls == []
    assert warnings == ["command unavailable"]
    assert window.worker is worker


def test_main_window_restart_schedules_only_after_worker_stops(monkeypatch):
    worker = FakeWorker(wait_result=True)
    window = SimpleNamespace(worker=worker)
    events: list[object] = []
    monkeypatch.setattr(main_window, "current_launch_command", lambda: ["daylens"])
    handle = SimpleNamespace(
        arm=lambda: events.append("arm"),
        cancel=lambda: events.append("cancel"),
    )
    monkeypatch.setattr(
        main_window,
        "schedule_restart",
        lambda command, deferred: events.append(
            ("schedule", command, deferred)
        )
        or handle,
    )
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        lambda candidate: (
            events.append("stopped")
            or WorkerShutdownResult(
                completed=True,
                worker=candidate,
                timeout_ms=42_000,
            )
        ),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        main_window.QApplication,
        "instance",
        staticmethod(lambda: SimpleNamespace(quit=lambda: events.append("quit"))),
    )

    MainWindow._restart_app(window)

    assert events == [
        ("schedule", ["daylens"], True),
        "stopped",
        "arm",
        "quit",
    ]


def test_main_window_restart_arm_failure_restores_recording_worker(monkeypatch):
    worker = FakeWorker(wait_result=True)
    events: list[object] = []
    replacement = object()
    window = SimpleNamespace(
        worker=worker,
        _restore_recording_worker=lambda: events.append("restore") or replacement,
    )
    handle = SimpleNamespace(
        arm=lambda: (_ for _ in ()).throw(OSError("arm unavailable")),
        cancel=lambda: events.append("cancel"),
    )
    monkeypatch.setattr(main_window, "current_launch_command", lambda: ["daylens"])
    monkeypatch.setattr(
        main_window,
        "schedule_restart",
        lambda command, deferred: events.append(("schedule", command, deferred))
        or handle,
    )
    monkeypatch.setattr(
        main_window,
        "stop_recording_worker_safely",
        lambda candidate: events.append(("stop", candidate))
        or WorkerShutdownResult(
            completed=True,
            worker=candidate,
            timeout_ms=15_000,
        ),
    )
    warnings: list[str] = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda _parent, _title, message: warnings.append(message),
    )

    MainWindow._restart_app(window)

    assert events == [
        ("schedule", ["daylens"], True),
        ("stop", worker),
        "cancel",
        "restore",
    ]
    assert window.worker is replacement
    assert warnings == ["arm unavailable"]


def test_tray_quit_timeout_keeps_tray_and_application_running(monkeypatch):
    worker = FakeWorker(wait_result=False)
    events: list[str] = []
    manager = TrayManager.__new__(TrayManager)
    manager.main_window = SimpleNamespace(worker=worker)
    manager.tray = SimpleNamespace(
        hide=lambda: events.append("hide"),
        showMessage=lambda *_args: events.append("warning"),
    )
    manager.app = SimpleNamespace(quit=lambda: events.append("quit"))
    monkeypatch.setattr(
        tray_manager,
        "stop_recording_worker_safely",
        lambda candidate: WorkerShutdownResult(
            completed=False,
            worker=candidate,
            timeout_ms=42_000,
            message="Still cleaning; retry later.",
        ),
    )

    manager._quit()

    assert events == ["warning"]
    assert manager.main_window.worker is worker


def test_bootstrap_timeout_does_not_close_shared_runtime(monkeypatch):
    worker = FakeWorker(wait_result=False)
    closed: list[bool] = []
    monkeypatch.setattr(
        gui_bootstrap,
        "stop_recording_worker_safely",
        lambda candidate: WorkerShutdownResult(
            completed=False,
            worker=candidate,
            timeout_ms=42_000,
            message="Still cleaning; retry later.",
        ),
    )
    monkeypatch.setattr(
        gui_bootstrap,
        "shutdown_runtime_state",
        lambda: closed.append(True),
    )

    result = gui_bootstrap.shutdown_gui_runtime(worker)

    assert result.completed is False
    assert result.worker is worker
    assert closed == []


def test_bootstrap_closes_shared_runtime_after_worker_finishes(monkeypatch):
    worker = FakeWorker(wait_result=True)
    events: list[str] = []
    monkeypatch.setattr(
        gui_bootstrap,
        "stop_recording_worker_safely",
        lambda candidate: (
            events.append("worker")
            or WorkerShutdownResult(
                completed=True,
                worker=candidate,
                timeout_ms=42_000,
            )
        ),
    )
    monkeypatch.setattr(
        gui_bootstrap,
        "shutdown_runtime_state",
        lambda: events.append("runtime"),
    )

    result = gui_bootstrap.shutdown_gui_runtime(worker)

    assert result.completed is True
    assert events == ["worker", "runtime"]
