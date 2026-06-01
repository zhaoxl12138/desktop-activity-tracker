#!/usr/bin/env python3
"""Desktop Activity Tracker - CLI + GUI entry point."""

import argparse
import os
import sys
import time
import signal
from datetime import datetime

import yaml

# Force UTF-8 output so Chinese characters don't crash on GBK terminals
if sys.stdout.encoding.upper() != 'UTF-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', errors='replace', buffering=1)

from . import get_app_root
from .window_detector import get_foreground_window_info
from .activity_detector import get_idle_seconds
from .classifier import Classifier
from . import database
from . import reporter
from . import exporter
from .utils import generate_default_config


CONFIG_FILENAME = "config/config.yaml"
REPORTS_DIRNAME = "reports"


def resolve_config_path():
    return os.path.join(get_app_root(), CONFIG_FILENAME)


def resolve_reports_dir():
    return os.path.join(get_app_root(), REPORTS_DIRNAME)


def load_config(config_path):
    if not os.path.exists(config_path):
        print(f"[INFO] 配置文件不存在，正在自动生成默认配置：{config_path}")
        generate_default_config(config_path)
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ── Commands ────────────────────────────────────────────────────────

def cmd_start(config, config_path):
    sample_interval = config.get("sample_interval_seconds", 5)
    db_path = database.get_db_path(config)

    clf = Classifier(config_path)
    conn = database.init_db(db_path)

    print(f"Desktop Activity Tracker v0.1.0")
    print(f"配置: {config_path}")
    print(f"数据库: {db_path}")
    print(f"采样间隔: {sample_interval}s | 空闲阈值: {config.get('idle_threshold_seconds', 60)}s")
    print("按 Ctrl+C 停止...\n")

    running = True
    last_error = ""

    def on_signal(sig, frame):
        nonlocal running
        print("\n正在停止...")
        running = False

    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)

    while running:
        try:
            now = datetime.now()
            idle_sec = get_idle_seconds()
            win_info = get_foreground_window_info()

            if win_info and (win_info.get("process_name") or win_info.get("window_title")):
                cat = clf.classify(win_info.get("process_name", ""), win_info.get("window_title", ""))
                is_effective = clf.is_effective(cat["active_rule"], idle_sec)
                is_user_active = idle_sec <= clf.idle_threshold

                sample = {
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": now.strftime("%Y-%m-%d"),
                    "process_name": win_info.get("process_name", ""),
                    "exe_path": win_info.get("exe_path", ""),
                    "window_title": win_info.get("window_title", ""),
                    "category_key": cat["category_key"],
                    "category_name": cat["category_name"],
                    "active_rule": cat["active_rule"],
                    "is_user_active": is_user_active,
                    "is_effective": is_effective,
                    "idle_seconds": round(idle_sec, 1),
                    "duration_seconds": sample_interval,
                }
            else:
                sample = {
                    "timestamp": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "date": now.strftime("%Y-%m-%d"),
                    "process_name": "system",
                    "exe_path": "",
                    "window_title": "idle/desktop",
                    "category_key": "other",
                    "category_name": "空闲",
                    "active_rule": "interactive_required",
                    "is_user_active": False,
                    "is_effective": False,
                    "idle_seconds": round(idle_sec, 1),
                    "duration_seconds": sample_interval,
                }

            database.insert_activity_log(conn, sample)

            status = f"[{sample['timestamp'][-8:]}] {sample['process_name']} | {sample['window_title'][:40]} | {sample['category_name']}"
            if sample["is_effective"]:
                status += " | effective=1"
            else:
                status += f" | effective=0 idle={sample['idle_seconds']}s"

            print(status.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding, errors='replace'))

            for _ in range(sample_interval):
                if not running:
                    break
                time.sleep(1)

        except Exception as e:
            err_msg = str(e)
            if err_msg != last_error:
                last_error = err_msg
                print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} {err_msg}", file=sys.stderr)

    conn.close()
    print("数据库已安全关闭。")


def cmd_report(config, args):
    db_path = database.get_db_path(config)

    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 `python -m desktop_activity_tracker.main start` 开始记录。")
        return

    if args.today:
        print(reporter.report_today(db_path))
    elif args.date:
        print(reporter.report_date(db_path, args.date))
    else:
        print(reporter.report_today(db_path))


def cmd_export(config, args):
    db_path = database.get_db_path(config)
    reports_daily_dir = os.path.join(resolve_reports_dir(), "daily")

    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 `python -m desktop_activity_tracker.main start` 开始记录。")
        return

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")

    if args.format == "csv":
        filepath = exporter.export_csv(db_path, date_str, reports_daily_dir)
        print(f"已导出 CSV: {filepath}")
    elif args.format == "md":
        filepath = exporter.export_markdown(db_path, date_str, reports_daily_dir)
        print(f"已导出 Markdown 日报: {filepath}")
        obsidian_path = config.get("obsidian_output_path", "").strip()
        if obsidian_path:
            dest = exporter.sync_to_obsidian(filepath, obsidian_path)
            if dest:
                print(f"已同步到 Obsidian: {dest}")
    else:
        csv_path = exporter.export_csv(db_path, date_str, reports_daily_dir)
        md_path = exporter.export_markdown(db_path, date_str, reports_daily_dir)
        print(f"已导出:\n  CSV: {csv_path}\n  Markdown: {md_path}")
        obsidian_path = config.get("obsidian_output_path", "").strip()
        if obsidian_path:
            dest = exporter.sync_to_obsidian(md_path, obsidian_path)
            if dest:
                print(f"已同步到 Obsidian: {dest}")


def cmd_weekly(config, args):
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 start 命令开始记录。")
        return

    reports_weekly_dir = os.path.join(resolve_reports_dir(), "weekly")
    today = datetime.now().date()
    year = args.year or today.year
    week = args.week or today.isocalendar()[1]

    try:
        filepath = exporter.export_weekly_report(db_path, year, week, reports_weekly_dir)
        print(f"已导出周报: {filepath}")
        obsidian_path = config.get("obsidian_output_path", "").strip()
        if obsidian_path:
            exporter.sync_to_obsidian(filepath, obsidian_path)
    except Exception as e:
        print(f"[ERROR] 周报生成失败: {e}")


def cmd_monthly(config, args):
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 start 命令开始记录。")
        return

    reports_monthly_dir = os.path.join(resolve_reports_dir(), "monthly")
    today = datetime.now().date()
    year = args.year or today.year
    month = args.month or today.month

    try:
        filepath = exporter.export_monthly_report(db_path, year, month, reports_monthly_dir)
        print(f"已导出月报: {filepath}")
        obsidian_path = config.get("obsidian_output_path", "").strip()
        if obsidian_path:
            exporter.sync_to_obsidian(filepath, obsidian_path)
    except Exception as e:
        print(f"[ERROR] 月报生成失败: {e}")


# ── GUI ──────────────────────────────────────────────────────────────

def cmd_gui():
    """Launch the PySide6 GUI with system tray."""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFont

    from .gui.worker import RecordingWorker
    from .gui.tray_manager import TrayManager
    from .gui.main_window import MainWindow

    app_root = get_app_root()
    config_path = resolve_config_path()
    reports_dir = resolve_reports_dir()

    # Ensure subdirs exist
    for sub in ("daily", "weekly", "monthly"):
        os.makedirs(os.path.join(reports_dir, sub), exist_ok=True)

    config = load_config(config_path)
    db_path = os.path.join(app_root, config.get("db_path", "data/usage.db"))

    # Ensure DB is initialized
    database.init_db(db_path)

    sample_interval = config.get("sample_interval_seconds", 5)

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei", 10))

    # Start background recording thread
    worker = RecordingWorker(config_path, db_path, sample_interval)
    worker.start()

    # Create tray icon
    tray = TrayManager(app, db_path, config)

    # Create main window
    window = MainWindow(app_root, config, db_path, config_path, reports_dir, worker)
    tray.set_main_window(window)
    window.show()

    exit_code = app.exec()

    # Clean shutdown
    worker.stop()
    worker.wait(3000)
    sys.exit(exit_code)


# ── Main ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Desktop Activity Tracker - 个人数字行为分析系统",
        prog="python -m desktop_activity_tracker.main"
    )
    subparsers = parser.add_subparsers(dest="command", help="可用命令")

    subparsers.add_parser("gui", help="启动图形界面 (默认)")
    subparsers.add_parser("start", help="命令行模式开始记录")
    subparsers.add_parser("today", help="快速查看今日统计")

    report_parser = subparsers.add_parser("report", help="查看使用统计")
    report_parser.add_argument("--today", action="store_true", help="查看今日统计")
    report_parser.add_argument("--date", type=str, help="查看指定日期统计 (YYYY-MM-DD)")

    export_parser = subparsers.add_parser("export", help="导出使用数据")
    export_parser.add_argument("--date", type=str, help="导出指定日期 (YYYY-MM-DD)")
    export_parser.add_argument("--format", type=str, choices=["csv", "md"], default="md",
                               help="导出格式: csv 或 md (默认md)")

    weekly_parser = subparsers.add_parser("weekly", help="生成周报")
    weekly_parser.add_argument("--year", type=int, help="ISO 年份 (默认今年)")
    weekly_parser.add_argument("--week", type=int, help="ISO 周数 (默认本周)")

    monthly_parser = subparsers.add_parser("monthly", help="生成月报")
    monthly_parser.add_argument("--year", type=int, help="年份 (默认今年)")
    monthly_parser.add_argument("--month", type=int, help="月份 1-12 (默认本月)")

    args = parser.parse_args()

    # Default: launch GUI
    if args.command is None or args.command == "gui":
        cmd_gui()
        return

    config_path = resolve_config_path()
    config = load_config(config_path)

    if args.command == "start":
        cmd_start(config, config_path)
    elif args.command == "today":
        db_path = database.get_db_path(config)
        if not os.path.exists(db_path):
            print("数据库不存在，请先运行 `python -m desktop_activity_tracker.main start` 开始记录。")
            return
        print(reporter.report_today(db_path))
    elif args.command == "report":
        cmd_report(config, args)
    elif args.command == "export":
        cmd_export(config, args)
    elif args.command == "weekly":
        cmd_weekly(config, args)
    elif args.command == "monthly":
        cmd_monthly(config, args)


if __name__ == "__main__":
    main()
