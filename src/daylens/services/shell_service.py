"""Shell-level helpers for top bar, tray tooltip, poetry, and quick reports."""

from __future__ import annotations

import os
from datetime import datetime

from .. import database, exporter
from ..utils import fmt_seconds
from .dashboard_service import category_seconds


def load_shell_summary(db_path: str, stats: dict | None = None) -> dict[str, int]:
    stats = stats or database.query_date_stats(db_path, datetime.now().strftime("%Y-%m-%d"))
    totals = stats.get("totals", {})
    category_totals = category_seconds(stats)
    return {
        "effective_seconds": int(totals.get("effective_seconds", 0) or 0),
        "work_seconds": int(category_totals["work"]),
        "entertainment_seconds": int(category_totals["entertainment"]),
        "social_seconds": int(category_totals["social"]),
    }


def load_poetry_hint(db_path: str, fallback_hint: str) -> str:
    try:
        row = database.get_random_poetry(db_path)
    except Exception:
        row = None
    if row:
        author = str(row.get("author", "") or "").strip()
        raw = str(row.get("content", "") or "").replace("\r", "\n")
        lines = [" ".join(line.split())[:20] for line in raw.split("\n") if line.strip()]
        lines = [line for line in lines if line]
        if not lines:
            return fallback_hint
        if len(lines) == 1:
            return f"{lines[0]} ——{author}" if author else lines[0]
        suffix = f" ——{author}" if author else ""
        return "\n".join(lines[:1] + [lines[1][:max(1, 20 - len(suffix))] + suffix])
    return fallback_hint


def generate_daily_report(db_path: str, reports_dir: str, obsidian_path: str = "") -> tuple[str, str | None]:
    os.makedirs(reports_dir, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    report_path = exporter.export_markdown(db_path, today, reports_dir)
    synced_path = None
    if obsidian_path:
        synced_path = exporter.sync_to_obsidian(report_path, obsidian_path)
    return report_path, synced_path


def build_tray_tooltip(db_path: str, paused: bool) -> str:
    summary = load_shell_summary(db_path)
    status = "已暂停" if paused else "记录中"
    return (
        "DayLens\n"
        f"活跃时间: {fmt_seconds(summary['effective_seconds'])}\n"
        f"工作学习: {fmt_seconds(summary['work_seconds'])}\n"
        f"娱乐休闲: {fmt_seconds(summary['entertainment_seconds'])}\n"
        f"状态: {status}"
    )
