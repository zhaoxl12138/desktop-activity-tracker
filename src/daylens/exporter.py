"""Export usage data to CSV and Markdown formats with efficiency score and suggestions."""

import os
import csv
import shutil
from datetime import datetime, timedelta
from . import database
from . import timeline
from .utils import fmt_seconds, normalize_category_display_name


def daily_report_path(output_dir: str, date_str: str) -> str:
    """Nested path: reports/daily/YYYY/YYYY-MM/YYYY-MM-DD.md"""
    year = date_str[:4]
    month = date_str[:7]
    return os.path.join(output_dir, year, month, f"{date_str}.md")


def _top_titles_by_category(db_path, date_str, limit=3):
    """Return {category_key: [title1, title2, title3]} of top window titles."""
    return database.query_top_titles_by_category(db_path, date_str, limit)


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
        suggestions.append("今日娱乐休闲时间超过90分钟，建议控制")

    # Rule 2: Entertainment > 90 min for 3 consecutive days
    trend = database.query_entertainment_trend(db_path, days=3)
    if len(trend) >= 3 and all(d["entertainment_seconds"] > 5400 for d in trend):
        suggestions.append("娱乐休闲时间连续3天超过90分钟，建议减少视频时间")

    # Rule 3: Low study/work ratio with sufficient total time
    if effective_sec > 0:
        work_ratio = work_sec / effective_sec
        if work_ratio < 0.3 and total_sec > 7200:
            suggestions.append("今日工作学习占比较低（<30%），建议增加工作学习时间")

    return suggestions, work_sec, video_sec


def export_csv(db_path, date_str, output_dir):
    stats = database.query_date_stats(db_path, date_str)
    filepath = daily_report_path(output_dir, date_str).replace(".md", ".csv")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

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
    filepath = daily_report_path(output_dir, date_str)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

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
    lines.append(f"- 娱乐休闲时间：{fmt_seconds(entertain_sec)}")
    lines.append(f"- 最长使用软件：{top_app_title or top_app}")
    lines.append(f"- 工作学习占比：{work_pct}%")
    lines.append(f"- 娱乐休闲占比：{entertain_pct}%")
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
        name = normalize_category_display_name(cat.get("category_key", ""), cat["category_name"])
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
            cat = normalize_category_display_name(s.get("category_key", ""), s.get("category_name") or "其他")
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
        lines.append("| 时间段 | 主状态 | 活跃 | 娱乐休闲 | 挂机 | Top应用 | 切换 |")
        lines.append("|---|---|---:|---:|---:|---|---:|")
        for b in active_blocks:
            cat_label = normalize_category_display_name("", b.dominant_category)
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


def _delta_text(curr, prev):
    """Return comparison text like '↑12%' or '↓15%' or '新增' or '-'.

    Values are in seconds.
    """
    if prev == 0:
        return "新增" if curr > 0 else "-"
    if curr == 0:
        return "-"
    diff_pct = round((curr - prev) / prev * 100)
    if diff_pct == 0:
        return "持平"
    direction = "↑" if diff_pct > 0 else "↓"
    return f"{direction}{abs(diff_pct)}%"


def _query_prev_period(read_conn, db_path, dates, period_type):
    """Query previous period (week or month) stats for comparison.

    Returns dict with keys: effective_seconds, work_seconds, video_seconds, active_days
    """
    from datetime import date, timedelta
    first = date.fromisoformat(dates[0])
    last = date.fromisoformat(dates[-1])
    if period_type == "week":
        prev_last = first - timedelta(days=1)
        prev_first = prev_last - timedelta(days=6)
    else:  # month
        prev_last = first - timedelta(days=1)
        prev_first = date(prev_last.year, prev_last.month, 1)
    prev_dates = []
    d = prev_first
    while d <= prev_last:
        prev_dates.append(d.strftime("%Y-%m-%d"))
        d += timedelta(days=1)

    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(prev_dates))
        row = conn.execute(
            f"""
            SELECT SUM(effective_seconds) as eff,
                   SUM(CASE WHEN category_key IN ('ai_tools','coding','reading','creative')
                       THEN effective_seconds ELSE 0 END) as work,
                   SUM(CASE WHEN category_key IN ('video','gaming')
                       THEN effective_seconds ELSE 0 END) as entertain,
                   COUNT(DISTINCT date) as days
            FROM activity_sessions
            WHERE date IN ({placeholders})
            """,
            prev_dates,
        ).fetchone()
    return {
        "effective_seconds": row["eff"] or 0,
        "work_seconds": row["work"] or 0,
        "video_seconds": row["entertain"] or 0,
        "active_days": row["days"] or 0,
    }


def _query_best_days(read_conn, db_path, dates, n=3):
    """Return top N days by work learning seconds: [(date, work_seconds, effective_seconds), ...]"""
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""
            SELECT date,
                   SUM(CASE WHEN category_key IN ('ai_tools','coding','reading','creative')
                       THEN effective_seconds ELSE 0 END) as work_seconds,
                   SUM(effective_seconds) as effective_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
            GROUP BY date
            ORDER BY work_seconds DESC
            LIMIT ?
            """,
            dates + [n],
        ).fetchall()
    return [(r["date"], r["work_seconds"], r["effective_seconds"]) for r in rows]


def _query_biggest_sink(read_conn, db_path, dates):
    """Return the top entertainment app: (process_name, effective_seconds, category_key) or None."""
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        row = conn.execute(
            f"""
            SELECT process_name, category_key,
                   SUM(effective_seconds) as effective_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
              AND category_key IN ('video', 'gaming')
            GROUP BY process_name
            ORDER BY effective_seconds DESC
            LIMIT 1
            """,
            dates,
        ).fetchone()
    if row and row["effective_seconds"]:
        return (row["process_name"], row["effective_seconds"], row["category_key"])
    return None


def _query_peak_hours(read_conn, db_path, dates):
    """Return the top 2 most active hour ranges like ['10:00-12:00', '14:00-16:00']."""
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""
            SELECT CAST(substr(start_time, 12, 2) AS INTEGER) as hour,
                   SUM(effective_seconds) as effective_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
              AND effective_seconds > 0
            GROUP BY hour
            ORDER BY effective_seconds DESC
            """,
            dates,
        ).fetchall()

    if not rows:
        return []

    # Merge adjacent hours into ranges
    hours_sorted = sorted([(r["hour"], r["effective_seconds"]) for r in rows],
                          key=lambda x: -x[1])
    ranges = []
    used = set()
    for h, _ in hours_sorted[:4]:
        if h in used:
            continue
        # Find if this hour is part of a cluster
        cluster = [h]
        for offset in [1, -1]:
            nh = h + offset
            while 0 <= nh <= 23 and nh in {r[0] for r in hours_sorted} and nh not in used:
                cluster.append(nh)
                used.add(nh)
                nh += offset
        used.add(h)
        cluster.sort()
        ranges.append(f"{cluster[0]:02d}:00-{cluster[-1]+1:02d}:00")
        if len(ranges) >= 2:
            break
    return ranges


def _query_keywords(read_conn, db_path, dates, n=8):
    """Extract top keywords from app names and window titles."""
    import re
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""
            SELECT process_name, normalized_title
            FROM activity_sessions
            WHERE date IN ({placeholders})
              AND effective_seconds > 0
            """,
            dates,
        ).fetchall()

    # Collect word frequencies
    word_freq = {}
    stop_words = {"exe", "com", "www", "http", "https", "the", "and", "for", "app",
                  "window", "page", "文件", "页面", "新建", "编辑", "查看"}

    for row in rows:
        proc = (row["process_name"] or "").replace(".exe", "")
        title = row["normalized_title"] or ""

        tokens = []
        # Extract meaningful tokens from process_name
        for token in re.split(r'[^a-zA-Z一-鿿㐀-䶿0-9]+', proc):
            token = token.strip()
            if len(token) >= 2 and token.lower() not in stop_words:
                tokens.append(token)

        # Extract meaningful tokens from window title
        for token in re.split(r'[\s\-—|/]+', title):
            token = token.strip()
            if len(token) >= 2 and token.lower() not in stop_words:
                tokens.append(token)

        for token in tokens:
            word_freq[token] = word_freq.get(token, 0) + 1

    # Return top N
    sorted_words = sorted(word_freq.items(), key=lambda x: -x[1])
    return [w for w, _ in sorted_words[:n]]


def _query_top_work_apps(read_conn, db_path, dates, n=3):
    """Return top N work-category apps by effective_seconds."""
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""
            SELECT process_name,
                   SUM(effective_seconds) as effective_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
              AND category_key IN ('ai_tools','coding','reading','creative')
            GROUP BY process_name
            ORDER BY effective_seconds DESC
            LIMIT ?
            """,
            dates + [n],
        ).fetchall()
    return [(r["process_name"], r["effective_seconds"]) for r in rows]


def _query_month_heatmap(read_conn, db_path, year, month):
    """Return list of (day, weekday, effective_seconds, work_seconds) for heatmap."""
    import calendar
    from datetime import date
    days_in_month = calendar.monthrange(year, month)[1]
    first = date(year, month, 1)

    with read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT date,
                   SUM(effective_seconds) as effective_seconds,
                   SUM(CASE WHEN category_key IN ('ai_tools','coding','reading','creative')
                       THEN effective_seconds ELSE 0 END) as work_seconds
            FROM activity_sessions
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date
            """,
            (first.strftime("%Y-%m-%d"), date(year, month, days_in_month).strftime("%Y-%m-%d")),
        ).fetchall()

    by_date = {}
    for r in rows:
        by_date[r["date"]] = (r["effective_seconds"] or 0, r["work_seconds"] or 0)

    result = []
    for day in range(1, days_in_month + 1):
        d = date(year, month, day)
        date_str = d.strftime("%Y-%m-%d")
        eff, work = by_date.get(date_str, (0, 0))
        result.append((day, d.weekday(), eff, work))
    return result


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


def _efficiency_grade(work_pct):
    """Return letter grade based on work percentage."""
    if work_pct >= 60:
        return "A"
    elif work_pct >= 50:
        return "B+"
    elif work_pct >= 40:
        return "B"
    elif work_pct >= 30:
        return "C"
    else:
        return "D"


def _gen_weekly_summary(stats, prev, best_days, peak_hours, sink, days_with_data):
    """Generate a natural-language weekly summary from data."""
    totals = stats["totals"]
    eff = totals["effective_seconds"]
    work = totals["work_seconds"]
    video = totals["video_seconds"]
    work_pct = round(work / eff * 100) if eff > 0 else 0
    grade = _efficiency_grade(work_pct)

    parts = []

    # Overall
    parts.append(f"本周总活跃{fmt_seconds(eff)}。")
    parts.append(f"工作学习占比{work_pct}%")

    # Week-over-week comparison
    if prev["effective_seconds"] > 0:
        work_delta = _delta_text(work, prev["work_seconds"])
        video_delta = _delta_text(video, prev["video_seconds"])
        if "↑" in work_delta or "↓" in work_delta:
            parts.append(f"，较上周{work_delta}")
        if "↑" in video_delta or "↓" in video_delta:
            parts.append(f"，娱乐{video_delta}")

    parts.append("。")

    # Peak hours
    if peak_hours:
        parts.append(f"最专注时段集中在{'、'.join(peak_hours)}。")

    # Top work apps for productivity mention
    work_keys = {"ai_tools", "coding", "reading", "creative"}
    work_apps = [a for a in stats["by_app"] if a.get("category_key") in work_keys][:3]
    if work_apps:
        app_names = [a["process_name"].replace(".exe", "") for a in work_apps]
        parts.append(f"{'、'.join(app_names)}是本周主要生产力工具。")

    # Entertainment
    if sink:
        sink_name, sink_sec, _ = sink
        sink_name = sink_name.replace(".exe", "")
        ent_total = video
        sink_pct = round(sink_sec / ent_total * 100) if ent_total > 0 else 0
        parts.append(f"娱乐时间主要集中在{sink_name}（{fmt_seconds(sink_sec)}，占娱乐{sink_pct}%）。")

    # Suggestion
    if work_pct < 30:
        parts.append("建议下周增加工作学习投入时间。")
    elif work_pct >= 50:
        parts.append("继续保持，下周争取更上一层楼。")

    parts.append(f"整体效率评分：{grade}。")

    return "".join(parts)


def _gen_monthly_summary(stats, prev, best_day, top_work_apps, days_with_data, total_days):
    """Generate a natural-language monthly summary from data."""
    totals = stats["totals"]
    eff = totals["effective_seconds"]
    work = totals["work_seconds"]
    video = totals["video_seconds"]
    work_pct = round(work / eff * 100) if eff > 0 else 0
    grade = _efficiency_grade(work_pct)

    parts = []
    parts.append(f"本月总活跃{fmt_seconds(eff)}。")
    parts.append(f"工作学习占比{work_pct}%")

    if prev["effective_seconds"] > 0:
        work_delta = _delta_text(work, prev["work_seconds"])
        if "↑" in work_delta or "↓" in work_delta:
            parts.append(f"，较上月{work_delta}")

    parts.append(f"。活跃天数{days_with_data}/{total_days}。")

    # Best day
    if best_day:
        date_str, best_work, _ = best_day
        parts.append(f"本月最专注一天是{date_str[-5:]}，工作学习{fmt_seconds(best_work)}。")

    # Top work apps
    if top_work_apps:
        app_names = [a[0].replace(".exe", "") for a in top_work_apps[:3]]
        parts.append(f"{'、'.join(app_names)}成为本月核心生产力工具。")

    # Entertainment
    ent_pct = round(video / eff * 100) if eff > 0 else 0
    if ent_pct > 20:
        parts.append(f"娱乐休闲占比{ent_pct}%，")
        if ent_pct > 40:
            parts.append("偏高，下月建议控制。")
        else:
            parts.append("在合理范围内。")

    parts.append(f"整体效率评分：{grade}。")

    return "".join(parts)


def export_weekly_report(db_path, year, week_number, output_dir):
    """Generate a comparison-driven weekly Markdown report.

    Focus: how does this week compare to last week? Trends, insights, suggestions.
    """
    dates = _week_dates(year, week_number)
    stats = database.query_date_range_stats(db_path, dates)
    daily = stats["daily"]
    totals = stats["totals"]
    prev = _query_prev_period(database.read_conn, db_path, dates, "week")
    best_days = _query_best_days(database.read_conn, db_path, dates, 3)
    sink = _query_biggest_sink(database.read_conn, db_path, dates)
    peak_hours = _query_peak_hours(database.read_conn, db_path, dates)
    os.makedirs(output_dir, exist_ok=True)

    start_date = dates[0]
    end_date = dates[-1]
    filename = f"{start_date}_{end_date}_weekly.md"
    filepath = os.path.join(output_dir, filename)

    days_with_data = sum(1 for d in daily if d["effective_seconds"] > 0)
    eff = totals["effective_seconds"]
    work = totals["work_seconds"]
    video = totals["video_seconds"]
    work_pct = round(work / eff * 100) if eff > 0 else 0
    activity_pct = round(eff / (eff + totals["idle_seconds"]) * 100) if eff > 0 else 0

    if days_with_data == 0:
        lines = [
            f"# {year}年第{week_number}周 个人数字行为周报",
            "",
            f"**{start_date} ~ {end_date}**",
            "",
            "数据不足，请保持记录以获取分析报告。",
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    lines = []
    lines.append(f"# {year}年第{week_number}周 个人数字行为周报")
    lines.append("")
    lines.append(f"**{start_date} ~ {end_date}** | 有效天数: {days_with_data}/7")
    lines.append("")

    # ── 1. Overview with week-over-week comparison ──
    lines.append("## 📊 本周概览")
    lines.append("")
    lines.append("| 指标 | 本周 | 环比 |")
    lines.append("|---|---|---|")
    lines.append(f"| 总活跃 | {fmt_seconds(eff)} | {_delta_text(eff, prev['effective_seconds'])} |")
    lines.append(f"| 工作学习 | {fmt_seconds(work)} | {_delta_text(work, prev['work_seconds'])} |")
    lines.append(f"| 娱乐休闲 | {fmt_seconds(video)} | {_delta_text(video, prev['video_seconds'])} |")
    lines.append(f"| 活跃占比 | {activity_pct}% | {_delta_text(eff, prev['effective_seconds'])} |")
    lines.append("")

    # ── 2. Daily trend ──
    lines.append("## 📈 本周趋势")
    lines.append("")
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    lines.append("| " + " | ".join(weekdays) + " |")
    lines.append("|" + "|".join([":---:"] * 7) + "|")

    # Work sparkline row
    work_spark = [d["work_seconds"] for d in daily]
    video_spark = [d["video_seconds"] for d in daily]
    max_val = max(max(work_spark), max(video_spark)) or 1

    work_cells = []
    video_cells = []
    for w, v in zip(work_spark, video_spark):
        work_bar = _sparkline([w], width=4, max_val=max_val)
        video_bar = _sparkline([v], width=4, max_val=max_val)
        work_cells.append(f"工作 {work_bar}")
        video_cells.append(f"娱乐 {video_bar}")
    lines.append("| " + " | ".join(work_cells) + " |")
    lines.append("| " + " | ".join(video_cells) + " |")

    # Daily values row
    day_values = []
    for d in daily:
        w = d["work_seconds"]
        v = d["video_seconds"]
        if w > 0 or v > 0:
            day_values.append(f"工{fmt_seconds(w)} 娱{fmt_seconds(v)}")
        else:
            day_values.append("—")
    lines.append("| " + " | ".join(day_values) + " |")
    lines.append("")

    # ── 3. Best 3 days ──
    lines.append("## 🏆 最专注的三天")
    lines.append("")
    medals = ["🥇", "🥈", "🥉"]
    for i, bd in enumerate(best_days):
        date_str, work_sec, _ = bd
        from datetime import date as dt_date
        d_obj = dt_date.fromisoformat(date_str)
        day_name = weekdays[d_obj.weekday()]
        lines.append(f"{medals[i]} **{day_name}** {date_str[-5:]}  {fmt_seconds(work_sec)}")
    if not best_days:
        lines.append("数据不足")
    lines.append("")

    # ── 4. Top 10 apps ──
    lines.append("## 💻 本周软件 TOP 10")
    lines.append("")
    for i, app in enumerate(stats["by_app"][:10]):
        proc = (app["process_name"] or "").replace(".exe", "")
        lines.append(f"{i+1}. **{proc}**  {fmt_seconds(app['effective_seconds'])}")
    lines.append("")

    # ── 5. Biggest time sink ──
    lines.append("## 🕳️ 本周最大时间黑洞")
    lines.append("")
    if sink:
        sink_name, sink_sec, sink_cat = sink
        sink_name_clean = sink_name.replace(".exe", "")
        ent_total = video
        sink_pct = round(sink_sec / ent_total * 100) if ent_total > 0 else 0
        emoji = "📺" if sink_cat == "video" else "🎮"
        lines.append(f"{emoji} **{sink_name_clean}**  累计 {fmt_seconds(sink_sec)}  （占娱乐 {sink_pct}%）")
    else:
        lines.append("本周没有明显的娱乐消费，很好！")
    lines.append("")

    # ── 6. AI summary ──
    lines.append("## 🤖 本周总结")
    lines.append("")
    lines.append(_gen_weekly_summary(stats, prev, best_days, peak_hours, sink, days_with_data))
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath


def export_monthly_report(db_path, year, month, output_dir):
    """Generate a comparison-driven monthly Markdown report.

    Focus: growth, habits, changes over the month. Heatmap, keywords, trends.
    """
    import calendar as cal_mod
    from datetime import date as dt_date

    dates = _month_dates(year, month)
    stats = database.query_date_range_stats(db_path, dates)
    daily = stats["daily"]
    totals = stats["totals"]
    prev = _query_prev_period(database.read_conn, db_path, dates, "month")
    heatmap = _query_month_heatmap(database.read_conn, db_path, year, month)
    keywords = _query_keywords(database.read_conn, db_path, dates, 8)
    best_days = _query_best_days(database.read_conn, db_path, dates, 1)
    top_work_apps = _query_top_work_apps(database.read_conn, db_path, dates, 3)
    os.makedirs(output_dir, exist_ok=True)

    filename = f"{year}-{month:02d}_monthly.md"
    filepath = os.path.join(output_dir, filename)

    days_with_data = sum(1 for d in daily if d["effective_seconds"] > 0)
    total_days = len(dates)
    eff = totals["effective_seconds"]
    work = totals["work_seconds"]
    video = totals["video_seconds"]
    work_pct = round(work / eff * 100) if eff > 0 else 0

    if days_with_data == 0:
        lines = [
            f"# {year}年{month}月 个人数字行为月报",
            "",
            f"**{dates[0]} ~ {dates[-1]}**",
            "",
            "数据不足，请保持记录以获取分析报告。",
        ]
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return filepath

    lines = []
    lines.append(f"# {year}年{month}月 个人数字行为月报")
    lines.append("")
    lines.append(f"**{dates[0]} ~ {dates[-1]}** | 有效天数: {days_with_data}/{total_days}")
    lines.append("")

    # ── 1. Monthly overview with comparison ──
    lines.append("## 📊 月度总览")
    lines.append("")
    lines.append("| 指标 | 本月 | 环比 |")
    lines.append("|---|---|---|")
    lines.append(f"| 总活跃 | {fmt_seconds(eff)} | {_delta_text(eff, prev['effective_seconds'])} |")
    lines.append(f"| 工作学习 | {fmt_seconds(work)} | {_delta_text(work, prev['work_seconds'])} |")
    lines.append(f"| 娱乐休闲 | {fmt_seconds(video)} | {_delta_text(video, prev['video_seconds'])} |")
    lines.append(f"| 活跃天数 | {days_with_data}/{total_days} | — |")
    lines.append("")

    # ── 2. Heatmap ──
    lines.append("## 🔥 月度热力图")
    lines.append("")

    # GitHub-style heatmap
    # Group by weeks
    weeks = []
    current_week = []
    for day, wday, eff_sec, _ in heatmap:
        current_week.append((day, wday, eff_sec))
        if wday == 6 or day == total_days:  # Sunday or last day
            weeks.append(current_week)
            current_week = []

    # Char mapping for intensity levels
    def heat_char(sec):
        if sec <= 0:
            return "·"
        elif sec < 1800:  # < 30min
            return "░"
        elif sec < 3600:  # 30-60min
            return "▒"
        elif sec < 7200:  # 1-2h
            return "▓"
        elif sec < 14400:  # 2-4h
            return "█"
        else:  # 4h+
            return "⬛"

    # Header row
    headers = ["一", "二", "三", "四", "五", "六", "日"]
    lines.append("```")
    lines.append("   " + " ".join(f"{h:>3}" for h in headers))
    for wk in weeks:
        cells = []
        for day, wday, eff_sec in wk:
            ch = heat_char(eff_sec)
            cells.append(f"{day:02d}{ch}")
        # Pad incomplete weeks
        row = " ".join(f"{c:>3}" for c in cells)
        lines.append(f"   {row}")
    lines.append("```")
    lines.append("*颜色越深越专注  ·无数据 ░<0.5h ▒0.5-1h ▓1-2h █2-4h ⬛>4h*")
    lines.append("")

    # ── 3. Best day ──
    lines.append("## ⭐ 月度最佳状态")
    lines.append("")
    if best_days:
        date_str, work_sec, _ = best_days[0]
        d_obj = dt_date.fromisoformat(date_str)
        weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        day_name = weekdays[d_obj.weekday()]
        lines.append(f"**{date_str}** {day_name}")
        lines.append(f"工作学习 **{fmt_seconds(work_sec)}**")
    else:
        lines.append("数据不足")
    lines.append("")

    # ── 4. Top 3 work apps ──
    lines.append("## 🏆 月度最强软件")
    lines.append("")
    if top_work_apps:
        for i, (proc, sec) in enumerate(top_work_apps):
            emoji = ["🥇", "🥈", "🥉"][i]
            proc_clean = proc.replace(".exe", "")
            lines.append(f"{emoji} **{proc_clean}**  {fmt_seconds(sec)}")
    else:
        lines.append("数据不足")
    lines.append("")

    # ── 5. Time distribution ──
    lines.append("## 📦 时间去向")
    lines.append("")
    # Aggregate into major groups
    work_keys = {"ai_tools", "coding", "reading", "creative"}
    entertainment_keys = {"video", "gaming"}
    system_keys = {"system", "tools", "browser_general", "other"}

    work_total = 0
    ent_total = 0
    sys_total = 0
    for cat in stats["by_category"]:
        ck = cat.get("category_key", "")
        sec = cat.get("effective_seconds", 0) or 0
        if ck in work_keys:
            work_total += sec
        elif ck in entertainment_keys:
            ent_total += sec
        else:
            sys_total += sec

    total = work_total + ent_total + sys_total
    bar_width = 20

    def _pct_bar(label, sec, pct):
        filled = round(pct / 100 * bar_width)
        bar = "█" * filled + "░" * (bar_width - filled)
        return f"| {label} | {pct}% | {bar} |"

    if total > 0:
        lines.append("| 类型 | 占比 | 分布 |")
        lines.append("|---|---|---|")
        work_pct_all = round(work_total / total * 100)
        ent_pct_all = round(ent_total / total * 100)
        sys_pct_all = 100 - work_pct_all - ent_pct_all
        lines.append(_pct_bar("工作学习", work_total, work_pct_all))
        lines.append(_pct_bar("娱乐休闲", ent_total, ent_pct_all))
        lines.append(_pct_bar("系统/其他", sys_total, sys_pct_all))
        lines.append(f"| **合计** | — | {fmt_seconds(total)} |")
    lines.append("")

    # ── 6. Keywords ──
    lines.append("## 🏷️ 本月关键词")
    lines.append("")
    if keywords:
        lines.append(" · ".join(keywords))
    else:
        lines.append("数据不足")
    lines.append("")

    # ── 7. AI summary ──
    lines.append("## 🤖 月度总结")
    lines.append("")
    best_day = best_days[0] if best_days else None
    lines.append(_gen_monthly_summary(stats, prev, best_day, top_work_apps, days_with_data, total_days))
    lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return filepath
