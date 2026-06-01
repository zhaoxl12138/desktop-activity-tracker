"""Generate human-readable usage reports from database."""

from datetime import datetime
from . import database


def _fmt_seconds(total_seconds):
    total_seconds = total_seconds or 0
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    if hours > 0:
        return f"{hours}小时{minutes}分钟"
    return f"{minutes}分钟"


def report_date(db_path, date_str):
    stats = database.query_date_stats(db_path, date_str)
    totals = stats["totals"]
    by_category = stats["by_category"]
    by_app_detail = stats["by_app_detail"]

    lines = []
    lines.append(f"{date_str} 使用统计")
    lines.append("=" * 50)
    lines.append("")
    lines.append(f"总有效时长：{_fmt_seconds(totals.get('effective_seconds', 0))}")
    lines.append(f"总空闲时长：{_fmt_seconds(totals.get('idle_seconds', 0))}")
    lines.append("")

    if by_category:
        lines.append("分类统计：")
        for cat in by_category:
            lines.append(f"  {cat['category_name']}：{_fmt_seconds(cat['effective_seconds'])}")
        lines.append("")

    if by_app_detail:
        lines.append("软件统计：")
        for app in by_app_detail[:20]:
            title_short = app["window_title"][:40] if app["window_title"] else "-"
            lines.append(f"  {app['process_name']} / {title_short}：{_fmt_seconds(app['effective_seconds'])}")
        lines.append("")

    return "\n".join(lines)


def report_today(db_path):
    today = datetime.now().strftime("%Y-%m-%d")
    return report_date(db_path, today)
