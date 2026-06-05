"""Export usage data to CSV and Markdown formats with efficiency score and suggestions."""

import os
import csv
import shutil
import sqlite3
from datetime import datetime, timedelta
from . import database
from . import timeline
from .utils import fmt_seconds


def _top_titles_by_category(db_path, date_str, limit=3):
    """Return {category_key: [title1, title2, title3]} of top window titles."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT category_key, normalized_title, SUM(effective_seconds) as total_sec
        FROM activity_sessions
        WHERE date = ? AND effective_seconds > 0 AND normalized_title != ''
        GROUP BY category_key, normalized_title
        ORDER BY category_key, total_sec DESC
    """, (date_str,)).fetchall()
    conn.close()

    result: dict[str, list[str]] = {}
    for row in rows:
        ck = row["category_key"]
        title = row["normalized_title"]
        if ck not in result:
            result[ck] = []
        if len(result[ck]) < limit:
            title_short = title[:28] + "…" if len(title) > 28 else title
            result[ck].append(title_short)
    return result


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

    work_cats = {"ai_tools", "coding", "reading", "creative"}
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
            suggestions.append("今日办公占比较低（<30%），建议增加办公时间")

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
    lines.append(f"- 活跃时间：{fmt_seconds(effective_sec)}")
    lines.append(f"- 挂机/空闲时间：{fmt_seconds(idle_sec)}")
    lines.append(f"- 娱乐时间：{fmt_seconds(entertain_sec)}")
    lines.append(f"- 最长使用软件：{top_app_title or top_app}")
    lines.append(f"- 办公占比：{work_pct}%")
    lines.append(f"- 娱乐占比：{entertain_pct}%")
    lines.append("")

    # ── 效率评分 ──
    if efficiency is not None:
        lines.append("## 效率评分")
        lines.append("")
        grade = "优秀" if efficiency >= 80 else ("良好" if efficiency >= 60 else ("一般" if efficiency >= 40 else "需改进"))
        lines.append(f"**{efficiency}/100** ({grade})")
        lines.append("")

    # ── 分类统计 (增强版: 占比 + 环比昨日 + Top应用) ──
    lines.append("## 分类统计")
    lines.append("")
    yesterday = (datetime.strptime(date_str, "%Y-%m-%d") - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_stats = database.query_date_stats(db_path, yesterday)
    yesterday_by_cat = {
        item["category_key"]: item.get("effective_seconds", 0) or 0
        for item in yesterday_stats.get("by_category", [])
    }
    # Build top app per category from by_app
    top_app_by_cat = {}
    for app in stats.get("by_app", []):
        ck = app.get("category_key")
        if ck not in top_app_by_cat or (app.get("effective_seconds", 0) or 0) > top_app_by_cat[ck][1]:
            top_app_by_cat[ck] = (app.get("process_name") or "", app.get("effective_seconds", 0) or 0)

    def _delta_text(curr: int, yesterday_val: int) -> str:
        if yesterday_val == 0:
            return "新增"
        diff = curr - yesterday_val
        if diff == 0:
            return "持平"
        direction = "↑" if diff > 0 else "↓"
        return f"{direction} {fmt_seconds(abs(diff))}"

    top_titles = _top_titles_by_category(db_path, date_str)

    lines.append("| 分类 | 时长 | 占比 | 环比昨日 | Top应用 | Top 内容 |")
    lines.append("|---|---:|---:|---|---|---|")
    for cat in stats["by_category"]:
        name = cat["category_name"]
        sec = cat.get("effective_seconds", 0) or 0
        pct = round(sec / effective_sec * 100) if effective_sec else 0
        delta = _delta_text(sec, yesterday_by_cat.get(cat["category_key"], 0))
        top = top_app_by_cat.get(cat["category_key"])
        top_label = top[0] if top else "-"
        titles = top_titles.get(cat["category_key"], [])
        titles_text = "、".join(titles) if titles else "-"
        lines.append(f"| {name} | {fmt_seconds(sec)} | {pct}% | {delta} | {top_label} | {titles_text} |")
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

    # ── 30分钟时间线 ──
    # ── 会话时间线 ──
    sessions = database.query_today_sessions(db_path, date_str)
    if sessions:
        lines.append("## 会话时间线")
        lines.append("")
        lines.append("| 时间段 | 应用 | 分类 | 有效 |")
        lines.append("|---|---|---:|---:|")
        for s in sessions:
            start = s.get("start_time", "") or ""
            end = s.get("end_time", "") or ""
            start_short = start[-8:-3] if len(start) >= 8 else start
            end_short = end[-8:-3] if len(end) >= 8 else end
            if start_short == end_short:
                # Same minute — include seconds to avoid "55:55-55:55"
                start_short = start[-8:] if len(start) >= 8 else start
                end_short = end[-8:] if len(end) >= 8 else end
            time_text = f"{start_short}-{end_short}" if start_short and end_short else start_short
            proc = s.get("process_name") or ""
            title = s.get("normalized_title") or s.get("window_title") or proc
            cat = s.get("category_name") or "其他"
            eff = s.get("effective_seconds", 0) or 0
            app_label = title[:30] if title else proc
            lines.append(
                f"| {time_text} | {app_label} | {cat} | {max(1, eff // 60)}分 |"
            )
        lines.append("")

    # ── 30分钟时间线概览 ──
    tl = timeline.build_timeline(db_path, date_str)
    active_blocks = [b for b in tl if b.dominant_category != "离线"]
    if active_blocks:
        lines.append("## 30分钟时间线概览")
        lines.append("")
        lines.append("| 时间段 | 主状态 | 活跃 | 娱乐 | 挂机 | Top应用 | 切换 |")
        lines.append("|---|---|---:|---:|---:|---|---:|")
        for b in active_blocks:
            cat_label = b.dominant_category
            top_label = b.top_title or b.top_app or "-"
            lines.append(
                f"| {b.slot} | {cat_label} | {b.effective_seconds // 60}分 | "
                f"{b.entertainment_seconds // 60}分 | {b.idle_seconds // 60}分 | "
                f"{top_label} | {b.switch_count} |"
            )
        lines.append("")

    # ── 今日专注时段 ──
    focus_blocks = timeline.identify_focus_blocks(tl)
    if focus_blocks:
        lines.append("## 今日专注时段")
        lines.append("")
        for fb in focus_blocks:
            lines.append(f"- {fb.start_slot}-{fb.end_slot} {fb.main_category} {fb.duration_minutes}分钟")
            for app in fb.top_apps[:3]:
                lines.append(f"  - {app}")
        lines.append("")

    # ── 碎片化情况 ──
    switch_count = database.query_session_count(db_path, date_str)
    frag_idx, frag_desc = timeline.calc_fragmentation(tl, switch_count)
    lines.append("## 碎片化情况")
    lines.append("")
    lines.append(f"今日窗口切换：{switch_count}次")
    lines.append(f"碎片化指数：{frag_idx}/100")
    lines.append(f"评价：{frag_desc}")
    lines.append("")

    # ── 一句话复盘 ──
    review = timeline.generate_one_line_review(tl, focus_blocks, frag_idx)
    lines.append("## 一句话复盘")
    lines.append("")
    lines.append(review)
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


# ── Weekly / Monthly report helpers ─────────────────────────────────

def _week_dates(year, week_number):
    """Return list of 7 date strings (Mon-Sun) for an ISO week number."""
    from datetime import date, timedelta
    # Find the Monday of the given ISO week
    jan4 = date(year, 1, 4)
    monday = jan4 - timedelta(days=jan4.isoweekday() - 1) + timedelta(weeks=week_number - 1)
    return [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]


def _month_dates(year, month):
    """Return list of date strings for all days in a month."""
    from datetime import date, timedelta
    import calendar
    days_in_month = calendar.monthrange(year, month)[1]
    first = date(year, month, 1)
    return [(first + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_in_month)]


def _sparkline(values, width=20, max_val=None):
    """Return a text-based sparkline bar using Unicode block characters."""
    if not values:
        return ""
    max_val = max_val or max(values) or 1
    chars = " ▁▂▃▄▅▆▇█"
    result = []
    for v in values:
        idx = min(8, int(v / max_val * 8)) if max_val > 0 else 0
        result.append(chars[idx])
    return "".join(result)


def _calculate_weekly_efficiency(daily):
    """Return 0-100 score and grade for the week."""
    work_total = sum(d["work_seconds"] for d in daily)
    video_total = sum(d["video_seconds"] for d in daily)
    eff_total = sum(d["effective_seconds"] for d in daily)
    if eff_total < 3600:
        return None, "数据不足"
    ratio = work_total / eff_total if eff_total > 0 else 0
    score = round(ratio * 100)
    if video_total > 5400 * 7:
        penalty = min(30, (video_total - 5400 * 7) // (1800 * 7) * 5)
        score = max(0, score - penalty)
    score = min(100, score)
    if score >= 80:
        grade = "优秀"
    elif score >= 60:
        grade = "良好"
    elif score >= 40:
        grade = "一般"
    else:
        grade = "需改进"
    return score, grade


def export_weekly_report(db_path, year, week_number, output_dir):
    """Generate a weekly summary Markdown report.

    Args:
        db_path: path to SQLite database
        year: ISO year (e.g. 2026)
        week_number: ISO week number (1-53)
        output_dir: directory to write the .md file

    Returns path to the generated report file.
    """
    dates = _week_dates(year, week_number)
    stats = database.query_date_range_stats(db_path, dates)
    daily = stats["daily"]
    totals = stats["totals"]
    os.makedirs(output_dir, exist_ok=True)

    start_date = dates[0]
    end_date = dates[-1]
    filename = f"{start_date}_{end_date}_weekly.md"
    filepath = os.path.join(output_dir, filename)

    score, grade = _calculate_weekly_efficiency(daily)
    days_with_data = sum(1 for d in daily if d["effective_seconds"] > 0)

    lines = []
    lines.append(f"# {year}年第{week_number}周 个人数字行为周报")
    lines.append("")
    lines.append(f"**{start_date} ~ {end_date}** | 有效天数: {days_with_data}/7")
    lines.append("")

    # ── 总览 ──
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 总电脑使用：{fmt_seconds(totals['total_seconds'])}")
    lines.append(f"- 活跃时间：{fmt_seconds(totals['effective_seconds'])}")
    lines.append(f"- 办公：{fmt_seconds(totals['work_seconds'])}")
    lines.append(f"- 视频娱乐：{fmt_seconds(totals['video_seconds'])}")
    lines.append(f"- 日均有效：{fmt_seconds(totals['effective_seconds'] // max(days_with_data, 1))}")
    lines.append("")

    if score is not None:
        lines.append(f"**周效率评分: {score}/100 ({grade})**")
        lines.append("")

    # ── 每日趋势 ──
    lines.append("## 每日趋势")
    lines.append("")
    lines.append("| 日期 | 有效时长 | 办公 | 视频娱乐 | 日效率 |")
    lines.append("|---|---:|---:|---:|---:|")
    work_spark = []
    video_spark = []
    for d in daily:
        date_label = d["date"][-5:]  # MM-DD
        eff = d["effective_seconds"]
        w = d["work_seconds"]
        v = d["video_seconds"]
        day_score = round(w / eff * 100) if eff > 0 else 0
        lines.append(f"| {date_label} | {fmt_seconds(eff)} | {fmt_seconds(w)} | {fmt_seconds(v)} | {day_score}% |")
        work_spark.append(w)
        video_spark.append(v)
    lines.append("")

    # Sparklines
    max_val = max(max(work_spark), max(video_spark)) or 1
    lines.append(f"办公趋势: `{_sparkline(work_spark, width=14, max_val=max_val)}`")
    lines.append(f"视频娱乐趋势: `{_sparkline(video_spark, width=14, max_val=max_val)}`")
    lines.append("")

    # ── 分类统计 ──
    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 分类 | 有效时长 | 日均 |")
    lines.append("|---|---:|---:|")
    for cat in stats["by_category"]:
        daily_avg = (cat["effective_seconds"] or 0) // max(days_with_data, 1)
        lines.append(f"| {cat['category_name']} | {fmt_seconds(cat['effective_seconds'])} | {fmt_seconds(daily_avg)} |")
    lines.append("")

    # ── 软件排行 ──
    lines.append("## 软件排行 (本周 TOP 10)")
    lines.append("")
    for app in stats["by_app"][:10]:
        lines.append(f"- **{app['process_name']}**：{fmt_seconds(app['effective_seconds'])}")
    lines.append("")

    # ── 建议 ──
    lines.append("## 建议")
    lines.append("")
    video_days = sum(1 for d in daily if d["video_seconds"] > 5400)
    work_days = sum(1 for d in daily if d["work_seconds"] > 7200)
    if video_days >= 4:
        lines.append(f"- 本周有 {video_days} 天娱乐时间超过90分钟，建议下周控制")
    if work_days < 3 and days_with_data >= 5:
        lines.append(f"- 本周仅 {work_days} 天办公时间超过2小时，建议增加办公投入")
    if days_with_data < 5:
        lines.append(f"- 本周仅 {days_with_data} 天有有效记录，建议提高电脑利用率")
    if not totals["video_seconds"] and not totals["work_seconds"]:
        lines.append("- 数据不足，请保持记录以获取分析建议")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def export_monthly_report(db_path, year, month, output_dir):
    """Generate a monthly summary Markdown report.

    Args:
        db_path: path to SQLite database
        year: year (e.g. 2026)
        month: month (1-12)
        output_dir: directory to write the .md file

    Returns path to the generated report file.
    """
    dates = _month_dates(year, month)
    stats = database.query_date_range_stats(db_path, dates)
    daily = stats["daily"]
    totals = stats["totals"]
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{year}-{month:02d}_monthly.md"
    filepath = os.path.join(output_dir, filename)

    days_with_data = sum(1 for d in daily if d["effective_seconds"] > 0)
    total_days = len(dates)
    daily_effective = [d["effective_seconds"] for d in daily if d["effective_seconds"] > 0]
    avg_daily_eff = sum(daily_effective) // max(len(daily_effective), 1)

    # Efficiency
    work_total = totals["work_seconds"]
    video_total = totals["video_seconds"]
    eff_total = totals["effective_seconds"]
    score, grade = _calculate_weekly_efficiency(daily)  # same logic works for month

    lines = []
    lines.append(f"# {year}年{month}月 个人数字行为月报")
    lines.append("")
    lines.append(f"**{dates[0]} ~ {dates[-1]}** | 有效天数: {days_with_data}/{total_days}")
    lines.append("")

    # ── 总览 ──
    lines.append("## 总览")
    lines.append("")
    lines.append(f"- 总电脑使用：{fmt_seconds(totals['total_seconds'])}")
    lines.append(f"- 活跃时间：{fmt_seconds(eff_total)}")
    lines.append(f"- 办公：{fmt_seconds(work_total)}")
    lines.append(f"- 视频娱乐：{fmt_seconds(video_total)}")
    lines.append(f"- 日均有效：{fmt_seconds(avg_daily_eff)}")
    lines.append(f"- 日均办公：{fmt_seconds(work_total // max(days_with_data, 1))}")
    lines.append(f"- 日均视频娱乐：{fmt_seconds(video_total // max(days_with_data, 1))}")
    lines.append("")

    if score is not None:
        lines.append(f"**月效率评分: {score}/100 ({grade})**")
        lines.append("")

    # ── 每周趋势 ──
    lines.append("## 每周趋势")
    lines.append("")
    # Group days by ISO week
    from collections import defaultdict
    weeks = defaultdict(lambda: {"work": 0, "video": 0, "eff": 0, "days": 0})
    for d in daily:
        from datetime import date as dt_date
        d_obj = dt_date.fromisoformat(d["date"])
        iso_year, iso_week, _ = d_obj.isocalendar()
        wkey = f"{iso_year}-W{iso_week:02d}"
        weeks[wkey]["work"] += d["work_seconds"]
        weeks[wkey]["video"] += d["video_seconds"]
        weeks[wkey]["eff"] += d["effective_seconds"]
        weeks[wkey]["days"] += 1

    lines.append("| 周 | 有效时长 | 办公 | 视频娱乐 | 周效率 |")
    lines.append("|---|---:|---:|---:|---:|")
    for wkey in sorted(weeks.keys()):
        w = weeks[wkey]
        w_score = round(w["work"] / w["eff"] * 100) if w["eff"] > 0 else 0
        lines.append(f"| {wkey} | {fmt_seconds(w['eff'])} | {fmt_seconds(w['work'])} | {fmt_seconds(w['video'])} | {w_score}% |")
    lines.append("")

    # ── 分类统计 ──
    lines.append("## 分类统计")
    lines.append("")
    lines.append("| 分类 | 有效时长 | 日均 | 占比 |")
    lines.append("|---|---:|---:|---:|")
    for cat in stats["by_category"]:
        daily_avg = (cat["effective_seconds"] or 0) // max(days_with_data, 1)
        pct = round(cat["effective_seconds"] / eff_total * 100) if eff_total > 0 else 0
        lines.append(f"| {cat['category_name']} | {fmt_seconds(cat['effective_seconds'])} | {fmt_seconds(daily_avg)} | {pct}% |")
    lines.append("")

    # ── 软件排行 ──
    lines.append("## 软件排行 (本月 TOP 15)")
    lines.append("")
    for app in stats["by_app"][:15]:
        pct = round(app["effective_seconds"] / eff_total * 100) if eff_total > 0 else 0
        lines.append(f"- **{app['process_name']}**：{fmt_seconds(app['effective_seconds'])} ({pct}%)")
    lines.append("")

    # ── 建议 ──
    lines.append("## 建议")
    lines.append("")
    if days_with_data < 15:
        lines.append(f"- 本月仅 {days_with_data} 天有记录，建议保持每日开机记录习惯")
    if video_total > 5400 * 30:
        lines.append("- 本月娱乐时间偏高，建议每月娱乐控制在 45 小时以内")
    if work_total > 0 and work_total / max(eff_total, 1) < 0.4:
        lines.append("- 本月办公占比偏低 (<40%)，下月可以设定办公目标")
    if not totals["video_seconds"] and not totals["work_seconds"]:
        lines.append("- 数据不足，请保持记录以获取分析建议")
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
