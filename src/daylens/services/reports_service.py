"""Report generation and file listing helpers for the GUI."""

from __future__ import annotations

import glob
import os
import shutil
from datetime import date, datetime

from .. import exporter


_REPORT_TYPE_NAMES = {
    "daily": "日报",
    "weekly": "周报",
    "monthly": "月报",
}


def list_report_rows(reports_dir: str, subdir: str, limit: int = 50) -> list[dict]:
    directory = os.path.join(reports_dir, subdir)
    files = sorted(glob.glob(os.path.join(directory, "**", "*.md"), recursive=True), reverse=True)[:limit]
    rows = []
    for file_path in files:
        filename = os.path.basename(file_path)
        label = filename.replace(".md", "").replace("_weekly", "").replace("_monthly", "")
        size_bytes = os.path.getsize(file_path)
        size_kb = max(1, (size_bytes + 1023) // 1024)
        modified_text = datetime.fromtimestamp(os.path.getmtime(file_path)).strftime("%Y-%m-%d %H:%M")
        rows.append(
            {
                "label": label,
                "filename": filename,
                "size_text": f"{size_kb} KB",
                "file_path": os.path.abspath(file_path),
                "modified_text": modified_text,
                "report_type": _REPORT_TYPE_NAMES.get(subdir, "报告"),
            }
        )
    return rows


def download_report(source_path: str, destination_path: str) -> str:
    source = os.path.abspath(source_path)
    destination = os.path.abspath(destination_path)
    if not os.path.isfile(source):
        raise FileNotFoundError(f"报告文件不存在：{source}")
    if os.path.normcase(source) == os.path.normcase(destination):
        return destination
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    shutil.copy2(source, destination)
    return destination


def download_reports(source_paths: list[str], destination_dir: str) -> dict:
    destination = os.path.abspath(destination_dir)
    os.makedirs(destination, exist_ok=True)
    saved_paths = []
    failures = []
    renamed_count = 0

    for source_path in source_paths:
        source = os.path.abspath(source_path)
        if not os.path.isfile(source):
            failures.append(
                {
                    "source_path": source_path,
                    "error": f"报告文件不存在：{source}",
                }
            )
            continue

        filename = os.path.basename(source)
        stem, extension = os.path.splitext(filename)
        target = os.path.join(destination, filename)
        suffix = 1
        while os.path.exists(target):
            target = os.path.join(destination, f"{stem} ({suffix}){extension}")
            suffix += 1
        if target != os.path.join(destination, filename):
            renamed_count += 1

        try:
            shutil.copy2(source, target)
            saved_paths.append(target)
        except Exception as exc:
            failures.append({"source_path": source_path, "error": str(exc)})

    return {
        "success_count": len(saved_paths),
        "renamed_count": renamed_count,
        "failure_count": len(failures),
        "saved_paths": saved_paths,
        "failures": failures,
        "destination_dir": destination,
    }


def open_report(file_path: str) -> None:
    path = os.path.abspath(file_path)
    if not os.path.exists(path):
        raise FileNotFoundError(f"报告文件不存在：{path}")
    os.startfile(path)


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
