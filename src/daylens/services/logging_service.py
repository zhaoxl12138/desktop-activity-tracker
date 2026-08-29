"""Persistent runtime logging for packaged and source GUI launches."""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from types import TracebackType


LOGGER = logging.getLogger(__name__)
_HANDLER_MARKER = "_daylens_file_handler"
_previous_excepthook = None
_qt_message_handler = None


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
