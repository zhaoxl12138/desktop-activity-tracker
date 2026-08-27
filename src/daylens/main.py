#!/usr/bin/env python3
"""DayLens - CLI + GUI entry point."""

from __future__ import annotations

import os
import sys

if __package__ is None or __package__ == "":
    _parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _parent not in sys.path:
        sys.path.insert(0, _parent)
    from daylens import database, reporter
    from daylens.cli import build_parser
    from daylens.console import configure_console_encoding
    from daylens.runtime import load_config, resolve_config_path, resolve_reports_dir
    from daylens.services.command_handlers import (
        handle_export,
        handle_monthly,
        handle_report,
        handle_start,
        handle_today,
        handle_weekly,
    )
    from daylens.services.gui_bootstrap import launch_gui
else:
    from . import database, reporter
    from .cli import build_parser
    from .console import configure_console_encoding
    from .runtime import load_config, resolve_config_path, resolve_reports_dir
    from .services.command_handlers import (
        handle_export,
        handle_monthly,
        handle_report,
        handle_start,
        handle_today,
        handle_weekly,
    )
    from .services.gui_bootstrap import launch_gui

configure_console_encoding()


def _run_qt_smoke() -> bool:
    """Exercise the bundled Qt DLLs and platform plugin without app data."""
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    pixmap = QPixmap(1, 1)
    app.processEvents()
    return not pixmap.isNull()


def main():
    parser = build_parser()
    args = parser.parse_args()

    if args.command is None or args.command == "gui":
        launch_gui()
        return

    config_path = resolve_config_path()
    config = load_config(config_path)

    if args.command == "start":
        handle_start(config, config_path)
    elif args.command == "today":
        handle_today(config)
    elif args.command == "report":
        handle_report(config, args)
    elif args.command == "export":
        handle_export(config, args, resolve_reports_dir())
    elif args.command == "weekly":
        handle_weekly(config, args, resolve_reports_dir())
    elif args.command == "monthly":
        handle_monthly(config, args, resolve_reports_dir())


if __name__ == "__main__":
    if os.environ.get("DAYLENS_QT_SMOKE") == "1":
        raise SystemExit(0 if _run_qt_smoke() else 1)
    main()
