"""Generate human-readable usage reports from database."""

from datetime import datetime
from . import database
from .utils import fmt_seconds


def report_date(db_path, date_str):
    stats = database.query_date_stats(db_path, date_str)
    totals = stats["totals"]
    by_category = stats["by_category"]
    by_app_detail = stats["by_app_detail"]

    lines = []
    lines.append(f"{date_str} 使用统计")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"总有效时长：{fmt_seconds(totals.get('effective_seconds', 0))}")
    lines.append(f"总空闲时长：{fmt_seconds(totals.get('idle_seconds', 0))}")
    lines.append("")

    if by_category:
        lines.append("分类统计：")
        for cat in by_category:
            lines.append(f"  {cat['category_name']}：{fmt_seconds(cat['effective_seconds'])}")
        lines.append("")

    if by_app_detail:
        lines.append("软件统计：")
        for app in by_app_detail[:20]:
            title_short = app["window_title"][:40] if app["window_title"] else "-"
            lines.append(f"  {app['process_name']} / {title_short}：{fmt_seconds(app['effective_seconds'])}")
        lines.append("")

    return "\n".join(lines)


def report_today(db_path):
    today = datetime.now().strftime("%Y-%m-%d")
    return report_date(db_path, today)
