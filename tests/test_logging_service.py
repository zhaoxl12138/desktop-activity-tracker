from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest

from daylens.services import logging_service


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    original_hook = sys.excepthook
    original_handlers = list(root.handlers)
    yield
    sys.excepthook = original_hook
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
