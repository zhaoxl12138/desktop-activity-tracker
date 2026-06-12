"""Report generation and file listing helpers for the GUI."""

from __future__ import annotations

import glob
import os
from datetime import date, datetime

from .. import exporter


def list_report_rows(reports_dir: str, subdir: str, limit: int = 50) -> list[tuple[str, str, str]]:
    directory = os.path.join(reports_dir, subdir)
    files = sorted(glob.glob(os.path.join(directory, "**", "*.md"), recursive=True), reverse=True)[:limit]
    rows = []
    for file_path in files:
        filename = os.path.basename(file_path)
        label = filename.replace(".md", "").replace("_weekly", "").replace("_monthly", "")
        size_kb = os.path.getsize(file_path) // 1024 if os.path.exists(file_path) else 0
        rows.append((label, filename, f"{size_kb} KB"))
    return rows


def generate_daily_report(db_path: str, reports_dir: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return exporter.export_markdown(db_path, today, os.path.join(reports_dir, "daily"))


def generate_weekly_report(db_path: str, reports_dir: str) -> str:
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    return exporter.export_weekly_report(db_path, iso_year, iso_week, os.path.join(reports_dir, "weekly"))


def generate_monthly_report(db_path: str, reports_dir: str) -> str:
    today = date.today()
    return exporter.export_monthly_report(db_path, today.year, today.month, os.path.join(reports_dir, "monthly"))


def sync_report_to_obsidian(filepath: str, obsidian_path: str) -> None:
    if obsidian_path and os.path.exists(filepath):
        exporter.sync_to_obsidian(filepath, obsidian_path)


def today_report_path(reports_dir: str) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    return exporter.daily_report_path(os.path.join(reports_dir, "daily"), today)


def weekly_report_path(reports_dir: str, year: int = None, week_number: int = None) -> str:
    """Return the file path for the weekly report (current or specified period)."""
    if year is None or week_number is None:
        today = date.today()
        year, week_number, _ = today.isocalendar()
    from ..exporter import _week_dates
    dates = _week_dates(year, week_number)
    return os.path.join(reports_dir, "weekly", f"{dates[0]}_{dates[-1]}_weekly.md")


def monthly_report_path(reports_dir: str, year: int = None, month: int = None) -> str:
    """Return the file path for the monthly report (current or specified period)."""
    if year is None or month is None:
        today = date.today()
        year = today.year
        month = today.month
    return os.path.join(reports_dir, "monthly", f"{year}-{month:02d}_monthly.md")


def weekly_report_exists(reports_dir: str) -> bool:
    """Check if the current period's weekly report file exists."""
    return os.path.exists(weekly_report_path(reports_dir))


def monthly_report_exists(reports_dir: str) -> bool:
    """Check if the current period's monthly report file exists."""
    return os.path.exists(monthly_report_path(reports_dir))


def should_generate_weekly() -> bool:
    """Check if it's time to auto-generate the weekly report (Sunday >= 23:00)."""
    now = datetime.now()
    return now.weekday() == 6 and now.hour >= 23


def should_generate_monthly() -> bool:
    """Check if it's time to auto-generate the monthly report (last day of month >= 23:00)."""
    import calendar
    now = datetime.now()
    last_day = calendar.monthrange(now.year, now.month)[1]
    return now.day == last_day and now.hour >= 23


def auto_generate_current_reports(db_path: str, reports_dir: str) -> list[str]:
    """Auto-generate weekly/monthly reports for the current period if they don't exist.

    On schedule trigger (Sunday >=23:00 / last day of month >=23:00),
    generate regardless of existence.

    Returns list of generated file paths.
    """
    generated = []

    should_gen_weekly = should_generate_weekly() or not weekly_report_exists(reports_dir)
    if should_gen_weekly:
        try:
            path = generate_weekly_report(db_path, reports_dir)
            if path:
                generated.append(path)
        except Exception as e:
            import sys
            print(f"[AutoReport] Weekly generation failed: {e}", file=sys.stderr)

    should_gen_monthly = should_generate_monthly() or not monthly_report_exists(reports_dir)
    if should_gen_monthly:
        try:
            path = generate_monthly_report(db_path, reports_dir)
            if path:
                generated.append(path)
        except Exception as e:
            import sys
            print(f"[AutoReport] Monthly generation failed: {e}", file=sys.stderr)

    return generated

