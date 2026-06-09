"""CLI parser construction."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="DayLens - 个人数字行为分析系统",
        prog="python -m daylens.main",
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
                               help="导出格式: csv 或 md (默认 md)")

    weekly_parser = subparsers.add_parser("weekly", help="生成周报")
    weekly_parser.add_argument("--year", type=int, help="ISO 年份 (默认今年)")
    weekly_parser.add_argument("--week", type=int, help="ISO 周数 (默认本周)")

    monthly_parser = subparsers.add_parser("monthly", help="生成月报")
    monthly_parser.add_argument("--year", type=int, help="年份 (默认今年)")
    monthly_parser.add_argument("--month", type=int, help="月份 1-12 (默认本月)")
    return parser
