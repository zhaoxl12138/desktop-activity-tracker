"""Startup-time database and rule bootstrap helpers."""

from __future__ import annotations

import sqlite3
import sys
import time

from .. import database
from .data_quality_service import inspect_data_quality


def ensure_readable_schema(
    db_path: str,
    *,
    timeout_seconds: float = 1.0,
) -> None:
    """Idempotently upgrade a database before a read-only workflow."""
    deadline = time.monotonic() + max(0.0, float(timeout_seconds))
    last_error: sqlite3.OperationalError | None = None
    while True:
        remaining = max(0.0, deadline - time.monotonic())
        busy_timeout_ms = max(1, min(100, int(remaining * 1000)))
        try:
            connection = database.init_db(
                db_path,
                busy_timeout_ms=busy_timeout_ms,
            )
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower():
                raise
            last_error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise last_error
            time.sleep(min(0.05, remaining))
            continue
        database.close_db(connection)
        return


def prepare_runtime_config(config: dict) -> tuple[dict, str]:
    db_path = database.get_db_path(config)
    ensure_readable_schema(db_path, timeout_seconds=5.0)
    database.merge_db_settings(config, db_path)
    try:
        tracker_config = config.get("tracker", {})
        sample_interval = tracker_config.get(
            "sample_interval_seconds",
            config.get("sample_interval_seconds", 1),
        )
        quality = inspect_data_quality(
            db_path,
            sample_interval_seconds=sample_interval,
        )
        if quality["issue_count"]:
            dates = ", ".join(quality.get("affected_dates", [])) or "unknown"
            print(
                f"[DataQuality] Found {quality['issue_count']} issue(s) "
                f"on dates: {dates}; use the manual repair preview to review",
                file=sys.stderr,
            )
    except Exception as exc:
        print(f"[DataQuality] Startup inspection failed: {exc}", file=sys.stderr)
    database.init_shared_read_conn(db_path)
    database.merge_custom_rules(config, db_path)
    return config, db_path


def load_bootstrap_state(db_path: str) -> tuple[dict, dict]:
    settings = database.load_settings(db_path) or {}
    custom_rules = database.load_custom_rules(db_path)
    return settings, custom_rules


def refresh_custom_rules(config: dict, db_path: str) -> None:
    database.merge_custom_rules(config, db_path)


def shutdown_runtime_state() -> None:
    database.close_shared_read_conn()
