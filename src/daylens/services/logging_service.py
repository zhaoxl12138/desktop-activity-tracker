"""Persistent runtime logging for packaged and source GUI launches."""

from __future__ import annotations

import json
import faulthandler
import logging
import os
import sys
import threading
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType


LOGGER = logging.getLogger(__name__)
_HANDLER_MARKER = "_daylens_file_handler"
_previous_excepthook = None
_previous_threading_excepthook = None
_qt_message_handler = None
_native_fault_file = None


class RuntimeDiagnostics:
    """Persist enough lifecycle state to identify an unclean prior exit."""

    def __init__(self, db_path: str | Path):
        self.state_path = Path(db_path).resolve().parent / "logs" / "runtime-state.json"
        self.started_at = _diagnostic_timestamp()

    def start(self) -> None:
        previous = self._read_state()
        if str(previous.get("status", "") or "") == "running":
            LOGGER.warning(
                "Previous DayLens run ended without a clean shutdown; "
                "pid=%s last_heartbeat=%s phase=%s",
                previous.get("pid", "unknown"),
                previous.get("last_heartbeat", "unknown"),
                previous.get("phase", "unknown"),
            )
        self._write_state(status="running", phase="startup")

    def heartbeat(self, phase: str = "running") -> None:
        self._write_state(status="running", phase=phase)

    def mark_clean_shutdown(self, *, exit_code: int) -> None:
        self._write_state(status="clean", phase="shutdown", exit_code=exit_code)

    def _read_state(self) -> dict:
        try:
            value = json.loads(self.state_path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _write_state(
        self,
        *,
        status: str,
        phase: str,
        exit_code: int | None = None,
    ) -> None:
        timestamp = _diagnostic_timestamp()
        payload = {
            "status": status,
            "phase": phase,
            "pid": os.getpid(),
            "started_at": self.started_at,
            "last_heartbeat": timestamp,
        }
        if exit_code is not None:
            payload["exit_code"] = int(exit_code)
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = self.state_path.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
            os.replace(temporary_path, self.state_path)
        except OSError:
            LOGGER.exception("Unable to persist DayLens runtime diagnostics")


def _diagnostic_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def start_runtime_diagnostics(db_path: str | Path) -> RuntimeDiagnostics:
    diagnostics = RuntimeDiagnostics(db_path)
    diagnostics.start()
    return diagnostics


def install_thread_exception_handler() -> None:
    global _previous_threading_excepthook
    if threading.excepthook is not _log_unhandled_thread_exception:
        _previous_threading_excepthook = threading.excepthook
        threading.excepthook = _log_unhandled_thread_exception


def install_native_fault_handler(db_path: str | Path) -> Path | None:
    """Write interpreter/native fault traces beside the canonical database."""
    global _native_fault_file
    fault_path = Path(db_path).resolve().parent / "logs" / "native-fault.log"
    try:
        fault_path.parent.mkdir(parents=True, exist_ok=True)
        if _native_fault_file is None or _native_fault_file.closed:
            _native_fault_file = fault_path.open("ab")
        faulthandler.enable(_native_fault_file, all_threads=True)
        return fault_path
    except (OSError, RuntimeError):
        LOGGER.exception("Unable to install native fault handler")
        return None


def _find_daylens_handler() -> RotatingFileHandler | None:
    for handler in logging.getLogger().handlers:
        if getattr(handler, _HANDLER_MARKER, False):
            return handler
    return None


def _log_unhandled_exception(
    exc_type: type[BaseException],
    exc_value: BaseException,
    traceback: TracebackType | None,
) -> None:
    logging.getLogger("daylens.unhandled").critical(
        "Unhandled exception",
        exc_info=(exc_type, exc_value, traceback),
    )
    previous = _previous_excepthook
    if previous is not None and previous is not _log_unhandled_exception:
        previous(exc_type, exc_value, traceback)


def _log_unhandled_thread_exception(args) -> None:
    logging.getLogger("daylens.unhandled").critical(
        "Unhandled thread exception; thread=%s",
        getattr(getattr(args, "thread", None), "name", "unknown"),
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )
    previous = _previous_threading_excepthook
    if previous is not None and previous is not _log_unhandled_thread_exception:
        previous(args)


def configure_app_logging(db_path: str | Path) -> Path | None:
    """Configure one rotating log next to the canonical database.

    Logging is diagnostic infrastructure and must never prevent recording from
    starting, so filesystem failures deliberately degrade to stderr logging.
    """

    global _previous_excepthook

    existing = _find_daylens_handler()
    if existing is not None:
        return Path(existing.baseFilename)

    log_path = Path(db_path).resolve().parent / "logs" / "daylens.log"
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            log_path,
            maxBytes=2_000_000,
            backupCount=3,
            encoding="utf-8",
        )
        setattr(handler, _HANDLER_MARKER, True)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s [%(threadName)s] %(name)s: %(message)s"
            )
        )
        root = logging.getLogger()
        root.addHandler(handler)
        if root.level > logging.INFO:
            root.setLevel(logging.INFO)

        if sys.excepthook is not _log_unhandled_exception:
            _previous_excepthook = sys.excepthook
            sys.excepthook = _log_unhandled_exception
        return log_path
    except Exception:
        logging.getLogger("daylens.startup").exception(
            "Unable to initialize persistent runtime logging"
        )
        return None


def install_qt_message_handler() -> bool:
    """Route Qt diagnostics into the same persistent application log."""

    global _qt_message_handler

    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler

        def handle_qt_message(message_type, context, message) -> None:
            levels = {
                QtMsgType.QtDebugMsg: logging.DEBUG,
                QtMsgType.QtInfoMsg: logging.INFO,
                QtMsgType.QtWarningMsg: logging.WARNING,
                QtMsgType.QtCriticalMsg: logging.ERROR,
                QtMsgType.QtFatalMsg: logging.CRITICAL,
            }
            location = ""
            if context is not None and getattr(context, "file", None):
                location = f" ({context.file}:{getattr(context, 'line', 0)})"
            logging.getLogger("daylens.qt").log(
                levels.get(message_type, logging.INFO),
                "%s%s",
                message,
                location,
            )

        _qt_message_handler = handle_qt_message
        qInstallMessageHandler(_qt_message_handler)
        return True
    except Exception:
        LOGGER.exception("Unable to install Qt message handler")
        return False
