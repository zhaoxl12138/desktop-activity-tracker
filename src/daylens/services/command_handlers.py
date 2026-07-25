"""CLI command handlers split from the legacy main entrypoint."""

from __future__ import annotations

import os
import signal
import sys
import time
from datetime import datetime

from .. import database, exporter, reporter
from ..activity_detector import get_idle_seconds
from ..classifier import Classifier
from ..session_tracker import SessionTracker
from .session_runtime_service import SessionRuntimeStore
from ..window_detector import get_foreground_window_info


def handle_start(config: dict, config_path: str) -> None:
    tracker_cfg = config.get("tracker", {})
    sample_interval = tracker_cfg.get("sample_interval_seconds", config.get("sample_interval_seconds", 1))
    flush_interval = tracker_cfg.get("flush_interval_seconds", config.get("flush_interval_seconds", 5))
    idle_threshold = tracker_cfg.get("idle_threshold_seconds", config.get("idle_threshold_seconds", 60))
    min_session = tracker_cfg.get("min_session_seconds", config.get("min_session_seconds", 2))

    db_path = database.get_db_path(config)
    classifier = Classifier(config_path, db_path)
    store = SessionRuntimeStore(db_path)

    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": sample_interval,
                "flush_interval_seconds": flush_interval,
                "idle_threshold_seconds": idle_threshold,
                "min_session_seconds": min_session,
            }
        },
        classifier=classifier,
        on_session_end=store.persist_session,
        on_flush=store.persist_session,
    )

    print("DayLens v1.5.3")
    print(f"配置: {config_path}")
    print(f"数据库: {db_path}")
    print(f"采样间隔: {sample_interval}s | 刷盘间隔: {flush_interval}s")
    print(f"空闲阈值: {idle_threshold}s | 最短 session: {min_session}s")
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
            idle_sec = get_idle_seconds()
            win_info = get_foreground_window_info()
            snapshot = tracker.tick(idle_sec, win_info)
            if snapshot is not None:
                status = _format_snapshot_status(snapshot)
                try:
                    print(status)
                except UnicodeEncodeError:
                    print(status.encode("ascii", errors="replace").decode("ascii"))
            time.sleep(sample_interval)
        except Exception as exc:
            err_msg = str(exc)
            if err_msg != last_error:
                last_error = err_msg
                print(f"[ERROR] {datetime.now().strftime('%H:%M:%S')} {err_msg}", file=sys.stderr)

    try:
        tracker.finish_current("shutdown")
    finally:
        store.close()
    print("数据库已安全关闭。")


def handle_report(config: dict, args) -> None:
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 `python -m daylens.main start` 开始记录。")
        return
    if args.today:
        print(reporter.report_today(db_path))
    elif args.date:
        print(reporter.report_date(db_path, args.date))
    else:
        print(reporter.report_today(db_path))


def handle_export(config: dict, args, reports_dir: str) -> None:
    db_path = database.get_db_path(config)
    reports_daily_dir = os.path.join(reports_dir, "daily")
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 `python -m daylens.main start` 开始记录。")
        return

    date_str = args.date or datetime.now().strftime("%Y-%m-%d")
    if args.format == "csv":
        filepath = exporter.export_csv(db_path, date_str, reports_daily_dir)
        print(f"已导出 CSV: {filepath}")
        return
    if args.format == "md":
        filepath = exporter.export_markdown(db_path, date_str, reports_daily_dir)
        print(f"已导出 Markdown 日报: {filepath}")
        _maybe_sync_obsidian(config, filepath)
        return

    csv_path = exporter.export_csv(db_path, date_str, reports_daily_dir)
    md_path = exporter.export_markdown(db_path, date_str, reports_daily_dir)
    print(f"已导出:\n  CSV: {csv_path}\n  Markdown: {md_path}")
    _maybe_sync_obsidian(config, md_path)


def handle_weekly(config: dict, args, reports_dir: str) -> None:
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 start 命令开始记录。")
        return
    today = datetime.now().date()
    year = args.year or today.year
    week = args.week or today.isocalendar()[1]
    try:
        filepath = exporter.export_weekly_report(db_path, year, week, os.path.join(reports_dir, "weekly"))
        print(f"已导出周报: {filepath}")
        _maybe_sync_obsidian(config, filepath)
    except Exception as exc:
        print(f"[ERROR] 周报生成失败: {exc}")


def handle_monthly(config: dict, args, reports_dir: str) -> None:
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 start 命令开始记录。")
        return
    today = datetime.now().date()
    year = args.year or today.year
    month = args.month or today.month
    try:
        filepath = exporter.export_monthly_report(db_path, year, month, os.path.join(reports_dir, "monthly"))
        print(f"已导出月报: {filepath}")
        _maybe_sync_obsidian(config, filepath)
    except Exception as exc:
        print(f"[ERROR] 月报生成失败: {exc}")


def handle_today(config: dict) -> None:
    db_path = database.get_db_path(config)
    if not os.path.exists(db_path):
        print("数据库不存在，请先运行 `python -m daylens.main start` 开始记录。")
        return
    print(reporter.report_today(db_path))


def _maybe_sync_obsidian(config: dict, filepath: str) -> None:
    obsidian_path = config.get("obsidian_output_path", "").strip()
    if obsidian_path:
        dest = exporter.sync_to_obsidian(filepath, obsidian_path)
        if dest:
            print(f"已同步到 Obsidian: {dest}")


def _format_snapshot_status(snapshot: dict) -> str:
    status = (
        f"[{snapshot['timestamp'][-8:]}] {snapshot['process_name']} | "
        f"{snapshot['normalized_title'][:30] or snapshot['window_title'][:30]} | "
        f"{snapshot['category_name']}"
    )
    if snapshot["is_effective"]:
        status += " | effective=1"
        status += f" | dur={snapshot['duration_seconds']}s eff={snapshot['effective_seconds']}s"
    else:
        status += f" | effective=0 idle={snapshot['idle_seconds']:.0f}s"
    return status
