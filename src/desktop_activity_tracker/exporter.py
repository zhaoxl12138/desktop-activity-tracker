"""Export usage data to CSV and Markdown formats with efficiency score and suggestions."""

import os
import csv
import shutil
from datetime import datetime
from . import database
from .utils import fmt_seconds


def _calculate_efficiency_score(work_sec, video_sec, total_effective_sec):
    """Return efficiency score 0-100, or None if insufficient data."""
    if total_effective_sec < 1800:  # < 30 minutes
        return None
    ratio = work_sec / total_effective_sec if total_effective_sec > 0 else 0
    score = round(ratio * 100)
    # Entertainment penalty: every 30min beyond 90min costs 5 points, max 30
    if video_sec > 5400:
        penalty = min(30, (video_sec - 5400) // 1800 * 5)
        score = max(0, score - penalty)
    return min(100, score)


def _generate_suggestions(db_path, today_date, stats):
    """Return a list of suggestion strings based on today's stats and trends."""
    suggestions = []
    totals = stats["totals"]
    effective_sec = totals.get("effective_seconds", 0) or 0
    idle_sec = totals.get("idle_seconds", 0) or 0
    total_sec = effective_sec + idle_sec

    work_cats = {"ai_tools", "coding", "reading"}
    work_sec = sum(
        c["effective_seconds"] for c in stats["by_category"]
        if c["category_key"] in work_cats
    )
    video_sec = sum(
        c["effective_seconds"] for c in stats["by_category"]
        if c["category_key"] == "video"
    )

    # Rule 1: Today's entertainment > 90 min
    if video_sec > 5400:
        suggestions.append("今日娱乐时间超过90分钟，建议控制")

    # Rule 2: Entertainment > 90 min for 3 consecutive days
    trend = database.query_entertainment_trend(db_path, days=3)
    if len(trend) >= 3 and all(d["entertainment_seconds"] > 5400 for d in trend):
        suggestions.append("娱乐时间连续3天超过90分钟，建议减少视频时间")

    # Rule 3: Low study/work ratio with sufficient total time
    if effective_sec > 0:
        work_ratio = work_sec / effective_sec
        if work_ratio < 0.3 and total_sec > 7200:
            suggestions.append("今日学习/工作占比较低（<30%），建议增加学习时间")

    return suggestions, work_sec, video_sec


def export_csv(db_path, date_str, output_dir):
    stats = database.query_date_stats(db_path, date_str)
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"usage_{date_str}.csv")

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)

        totals = stats["totals"]
        writer.writerow(["日期", "总有效时长(秒)", "总空闲时长(秒)", "总采样数"])
        writer.writerow([
            date_str,
            totals.get("effective_seconds", 0),
            totals.get("idle_seconds", 0),
            totals.get("total_samples", 0),
        ])
        writer.writerow([])

        writer.writerow(["分类统计"])
        writer.writerow(["分类Key", "分类名称", "有效时长(秒)", "空闲时长(秒)", "总时长(秒)"])
        for cat in stats["by_category"]:
            writer.writerow([
                cat["category_key"],
                cat["category_name"],
                cat["effective_seconds"],
                cat["idle_seconds"],
                cat["total_seconds"],
            ])
        writer.writerow([])

        writer.writerow(["软件详情"])
        writer.writerow(["进程名", "窗口标题", "有效时长(秒)"])
        for app in stats["by_app_detail"]:
            writer.writerow([
                app["process_name"],
                app["window_title"],
                app["effective_seconds"],
            ])

    return filepath


def export_markdown(db_path, date_str, output_dir):
    stats = database.query_date_stats(db_path, date_str)
    totals = stats["totals"]
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, f"{date_str}.md")

    effective_sec = totals.get("effective_seconds", 0) or 0
    idle_sec = totals.get("idle_seconds", 0) or 0
    total_sec = effective_sec + idle_sec

    suggestions, work_sec, video_sec = _generate_suggestions(db_path, date_str, stats)

    entertain_sec = video_sec
    work_pct = round(work_sec / effective_sec * 100) if effective_sec > 0 else 0
    entertain_pct = round(entertain_sec / effective_sec * 100) if effective_sec > 0 else 0
    efficiency = _calculate_efficiency_score(work_sec, video_sec, effective_sec)

    top_app = stats["by_app_detail"][0]["process_name"] if stats["by_app_detail"] else "-"
    top_app_title = stats["by_app_detail"][0]["window_title"] if stats["by_app_detail"] else ""

    lines = []
    lines.append(f"# {date_str} 个人数字行为日报")
    lines.append("")

    # ── 总览 ──
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 总电脑使用：{fmt_seconds(total_sec)}")
    lines.append(f"- 有效时间：{fmt_seconds(effective_sec)}")
    lines.append(f"- 挂机/空闲时间：{fmt_seconds(idle_sec)}")
    lines.append(f"- 娱乐时间：{fmt_seconds(entertain_sec)}")
    lines.append(f"- 最长使用软件：{top_app_title or top_app}")
    lines.append(f"- 学习/工作占比：{work_pct}%")
    lines.append(f"- 娱乐占比：{entertain_pct}%")
    lines.append("")

    # ── 效率评分 ──
    if efficiency is not None:
        lines.append("## 效率评分")
        lines.append("")
        grade = "优秀" if efficiency >= 80 else ("良好" if efficiency >= 60 else ("一般" if efficiency >= 40 else "需改进"))
        lines.append(f"**{efficiency}/100** ({grade})")
        lines.append("")

    # ── 分类统计 ──
    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 分类 | 有效时长 |")
    lines.append("|---|---:|")
    for cat in stats["by_category"]:
        lines.append(f"| {cat['category_name']} | {fmt_seconds(cat['effective_seconds'])} |")
    lines.append("")

    # ── 软件排行 ──
    lines.append("## 软件排行")
    lines.append("")
    seen = set()
    for app in stats["by_app_detail"][:20]:
        key = _extract_title_key(app["window_title"] or app["process_name"])
        if key not in seen:
            seen.add(key)
            lines.append(f"- {key}：{fmt_seconds(app['effective_seconds'])}")
    lines.append("")

    # ── 建议 ──
    if suggestions:
        lines.append("## 建议")
        lines.append("")
        for s in suggestions:
            lines.append(f"- {s}")
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def _extract_title_key(window_title):
    """Extract the most meaningful keyword from a window title."""
    if not window_title:
        return "Unknown"
    for suffix in [" - Google Chrome", " - Microsoft Edge", " - Visual Studio Code",
                   " - Obsidian", " — Mozilla Firefox", " - YouTube"]:
        if suffix in window_title:
            return window_title.replace(suffix, "").strip()[:40]
    for sep in [" - ", " — ", " | "]:
        if sep in window_title:
            return window_title.split(sep)[0].strip()[:40]
    return window_title[:40]


def sync_to_obsidian(filepath, obsidian_output_path):
    """Copy the report file to an Obsidian vault directory."""
    if not obsidian_output_path or not os.path.exists(filepath):
        return
    try:
        os.makedirs(obsidian_output_path, exist_ok=True)
        dest = os.path.join(obsidian_output_path, os.path.basename(filepath))
        shutil.copy2(filepath, dest)
        return dest
    except Exception as e:
        print(f"[WARN] Obsidian 同步失败: {e}")
        return None
