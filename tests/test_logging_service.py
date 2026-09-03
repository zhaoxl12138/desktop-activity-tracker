from __future__ import annotations

import logging
import json
import sys
import threading
from types import SimpleNamespace
from pathlib import Path

import pytest

from daylens.services import logging_service


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    original_hook = sys.excepthook
    original_thread_hook = threading.excepthook
    original_handlers = list(root.handlers)
    yield
    sys.excepthook = original_hook
    threading.excepthook = original_thread_hook
    for handler in list(root.handlers):
        if handler not in original_handlers:
            root.removeHandler(handler)
            handler.close()


def _flush_daylens_handlers() -> None:
    for handler in logging.getLogger().handlers:
        if getattr(handler, "_daylens_file_handler", False):
            handler.flush()


def test_configure_app_logging_writes_beside_database(tmp_path):
    db_path = tmp_path / "usage.db"

    log_path = logging_service.configure_app_logging(db_path)
    logging.getLogger("daylens.test").warning("persistent sentinel")
    _flush_daylens_handlers()

    assert log_path == tmp_path / "logs" / "daylens.log"
    assert "persistent sentinel" in log_path.read_text(encoding="utf-8")


def test_configure_app_logging_is_idempotent_and_rotating(tmp_path):
    db_path = tmp_path / "usage.db"

    first_path = logging_service.configure_app_logging(db_path)
    second_path = logging_service.configure_app_logging(db_path)
    handlers = [
        handler
        for handler in logging.getLogger().handlers
        if getattr(handler, "_daylens_file_handler", False)
    ]

    assert first_path == second_path
    assert len(handlers) == 1
    assert handlers[0].maxBytes == 2_000_000
    assert handlers[0].backupCount == 3


def test_unhandled_exception_hook_persists_traceback(tmp_path):
    log_path = logging_service.configure_app_logging(tmp_path / "usage.db")

    try:
        raise RuntimeError("unhandled sentinel")
    except RuntimeError:
        exc_type, exc_value, traceback = sys.exc_info()
        sys.excepthook(exc_type, exc_value, traceback)
    _flush_daylens_handlers()

    content = log_path.read_text(encoding="utf-8")
    assert "Unhandled exception" in content
    assert "RuntimeError: unhandled sentinel" in content


def test_configure_app_logging_does_not_break_startup_when_file_open_fails(
    monkeypatch, tmp_path
):
    def fail_handler(*args, **kwargs):
        raise OSError("read only")

    monkeypatch.setattr(logging_service, "RotatingFileHandler", fail_handler)

    assert logging_service.configure_app_logging(tmp_path / "usage.db") is None


def test_runtime_diagnostics_marks_stale_run_and_clean_shutdown(tmp_path):
    db_path = tmp_path / "usage.db"
    log_path = logging_service.configure_app_logging(db_path)
    state_path = tmp_path / "logs" / "runtime-state.json"
    state_path.write_text(
        json.dumps({"status": "running", "pid": 4321, "last_heartbeat": "old"}),
        encoding="utf-8",
    )

    diagnostics = logging_service.start_runtime_diagnostics(db_path)
    _flush_daylens_handlers()

    running_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert running_state["status"] == "running"
    assert running_state["phase"] == "startup"
    assert "Previous DayLens run ended without a clean shutdown" in log_path.read_text(
        encoding="utf-8"
    )

    diagnostics.mark_clean_shutdown(exit_code=0)
    clean_state = json.loads(state_path.read_text(encoding="utf-8"))
    assert clean_state["status"] == "clean"
    assert clean_state["exit_code"] == 0


def test_thread_exception_hook_persists_background_traceback(monkeypatch, tmp_path):
    log_path = logging_service.configure_app_logging(tmp_path / "usage.db")
    monkeypatch.setattr(threading, "excepthook", lambda _args: None)
    logging_service.install_thread_exception_handler()

    try:
        raise RuntimeError("thread sentinel")
    except RuntimeError:
        exc_type, exc_value, traceback = sys.exc_info()
        threading.excepthook(
            SimpleNamespace(
                exc_type=exc_type,
                exc_value=exc_value,
                exc_traceback=traceback,
                thread=threading.current_thread(),
            )
        )
    _flush_daylens_handlers()

    content = log_path.read_text(encoding="utf-8")
    assert "Unhandled thread exception" in content
    assert "RuntimeError: thread sentinel" in content


def test_native_fault_handler_targets_dedicated_crash_log(monkeypatch, tmp_path):
    captured = {}

    def fake_enable(file, *, all_threads):
        captured["path"] = Path(file.name)
        captured["all_threads"] = all_threads

    monkeypatch.setattr(logging_service.faulthandler, "enable", fake_enable)

    fault_path = logging_service.install_native_fault_handler(tmp_path / "usage.db")

    assert fault_path == tmp_path / "logs" / "native-fault.log"
    assert captured == {"path": fault_path, "all_threads": True}
