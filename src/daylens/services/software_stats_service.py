"""Helpers for the software stats page."""

from __future__ import annotations

import os
import shutil
import tempfile
from datetime import datetime

from .. import database, exporter
from ..utils import fmt_seconds, normalize_category_bucket_key, normalize_category_display_name


def load_software_rows(db_path: str, display_name_mapping: dict[str, str]) -> list[dict[str, str]]:
    today = datetime.now().strftime("%Y-%m-%d")
    stats = database.query_date_stats(db_path, today)
    details = stats.get("by_app_detail", [])
    total_eff = stats.get("totals", {}).get("effective_seconds", 0) or 1
    fallback_categories = {}
    for category_app in stats.get("by_app", []):
        process_name = category_app.get("process_name", "")
        fallback_categories.setdefault(process_name, category_app)

    rows: list[dict[str, str]] = []
    for app in details:
        process_name = app.get("process_name", "")
        display_name = display_name_mapping.get(process_name, process_name)
        title = (app.get("window_title", "") or "-")[:60]
        raw_category_name = str(app.get("category_name", "") or "")
        raw_category_key = str(app.get("category_key", "") or "")
        if not raw_category_key and not raw_category_name:
            fallback = fallback_categories.get(process_name, {})
            raw_category_name = str(fallback.get("category_name", "") or "")
            raw_category_key = str(fallback.get("category_key", "") or "")
        category_name = normalize_category_display_name(
            raw_category_key,
            raw_category_name,
        )
        category_key = normalize_category_bucket_key(
            raw_category_key,
            raw_category_name,
        )
        seconds = app.get("effective_seconds", 0) or 0
        rows.append(
            {
                "software": display_name,
                "title": title,
                "category_name": category_name,
                "category_key": category_key,
                "duration": fmt_seconds(seconds),
                "percent": f"{round(seconds / total_eff * 100)}%" if total_eff > 0 else "0%",
            }
        )
    return rows


def export_software_csv(db_path: str, target_path: str) -> str:
    return _export_to_target(exporter.export_csv, db_path, target_path)


def export_software_markdown(db_path: str, target_path: str) -> str:
    return _export_to_target(exporter.export_markdown, db_path, target_path)


def _export_to_target(export_func, db_path: str, target_path: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    target = os.path.abspath(target_path)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="daylens-export-") as temp_dir:
        generated = export_func(db_path, today, temp_dir)
        shutil.copy2(generated, target)
    return target
