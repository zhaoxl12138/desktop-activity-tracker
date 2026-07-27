"""Build homepage view data outside the Qt page layer."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from .. import database, timeline
from ..utils import fmt_seconds

WORK_KEYS = {"ai_tools", "coding", "office", "reading", "creative"}
ENTERTAINMENT_KEYS = {"video", "gaming"}


def _rolling_date_strings(end_date: date, days: int) -> list[str]:
    """Return an inclusive rolling window ordered from oldest to newest."""
    count = max(0, int(days))
    return [
        (end_date - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in reversed(range(count))
    ]


def resolve_display_name(
    process_name: str,
    app_details: list[dict],
    display_name_mapping: dict[str, str],
) -> str:
    """Resolve an application label without touching any Qt widget state."""
    wrapper_processes = {
        "WindowsTerminal.exe",
        "cmd.exe",
        "powershell.exe",
        "Code.exe",
        "Cursor.exe",
    }
    if process_name in wrapper_processes:
        top_title = ""
        top_seconds = 0
        for detail in app_details:
            if detail.get("process_name") != process_name:
                continue
            seconds = int(detail.get("effective_seconds", 0) or 0)
            if seconds > top_seconds:
                top_seconds = seconds
                top_title = str(detail.get("window_title", "") or "")
        for keyword, label in (
            ("Claude Code", "Claude Code"),
            ("Codex", "Codex"),
            ("Cursor", "Cursor"),
        ):
            if keyword.casefold() in top_title.casefold():
                return label
    return display_name_mapping.get(process_name) or process_name


def category_seconds(stats: dict) -> dict[str, int]:
    totals = {"work": 0, "social": 0, "entertainment": 0, "tools": 0}
    for item in stats.get("by_category", []):
        seconds = int(item.get("effective_seconds", 0) or 0)
        category_key = item.get("category_key")
        if category_key in WORK_KEYS:
            totals["work"] += seconds
        elif category_key == "social":
            totals["social"] += seconds
        elif category_key in ENTERTAINMENT_KEYS:
            totals["entertainment"] += seconds
        elif category_key == "tools":
            totals["tools"] += seconds
    return totals


def build_distribution_sections(stats: dict, effective_seconds: int) -> list[dict[str, object]]:
    category_totals = category_seconds(stats)
    other_seconds = max(
        int(effective_seconds or 0)
        - category_totals["work"]
        - category_totals["social"]
        - category_totals["entertainment"],
        0,
    )
    sections = [
        {"category_key": "work", "label": "工作学习", "seconds": category_totals["work"]},
        {"category_key": "video", "label": "娱乐休闲", "seconds": category_totals["entertainment"]},
        {"category_key": "social", "label": "社交通讯", "seconds": category_totals["social"]},
    ]
    if other_seconds > 0:
        sections.append({"category_key": "other", "label": "其他", "seconds": other_seconds})
    return sections


def build_day_over_day_comparison(today_stats: dict, yesterday_stats: dict) -> dict[str, dict[str, int | str]]:
    today = category_seconds(today_stats)
    yesterday = category_seconds(yesterday_stats)
    comparison = {}
    mapping = {
        "work": "work",
        "social": "social",
        "entertainment": "entertainment",
    }
    for key, source_key in mapping.items():
        today_value = today[source_key]
        yesterday_value = yesterday[source_key]
        delta = today_value - yesterday_value
        if today_value == 0 and yesterday_value == 0:
            direction = "empty"
        elif abs(delta) < 60:
            direction = "flat"
        elif delta > 0:
            direction = "up"
        else:
            direction = "down"
        comparison[key] = {
            "today_seconds": today_value,
            "yesterday_seconds": yesterday_value,
            "delta_seconds": delta,
            "direction": direction,
        }
    return comparison


def build_top_app_rows(stats: dict, resolve_display) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    app_details = stats.get("by_app_detail", [])
    for item in stats.get("by_app", []):
        process_name = item.get("process_name") or "Unknown"
        display_name = resolve_display(process_name, app_details)
        seconds = int(item.get("effective_seconds", 0) or 0)
        bucket = merged.setdefault(display_name, {"process_name": process_name, "display_name": display_name, "seconds": 0})
        bucket["seconds"] = int(bucket["seconds"]) + seconds
    return sorted(merged.values(), key=lambda item: -int(item["seconds"]))[:9]


def build_hourly_series(sessions: list[dict]) -> list[int]:
    hour_minutes = [0.0] * 24
    for session in sessions:
        start_dt = _parse_dt(session.get("start_time", ""))
        end_dt = _parse_dt(session.get("end_time", ""))
        effective_seconds = float(session.get("effective_seconds", 0) or 0)
        if effective_seconds <= 0 or start_dt is None or end_dt is None:
            continue
        total_span = (end_dt - start_dt).total_seconds()
        if total_span <= 0:
            hour_minutes[start_dt.hour] += effective_seconds / 60.0
            continue
        current = start_dt
        while current < end_dt:
            hour = current.hour
            next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(end_dt, next_hour)
            segment_seconds = (segment_end - current).total_seconds()
            ratio = segment_seconds / total_span
            hour_minutes[hour] += (effective_seconds * ratio) / 60.0
            current = segment_end
    return [round(value) for value in hour_minutes]


def build_hourly_series_split(sessions: list[dict]) -> dict[str, list[int]]:
    """Return hourly minutes split by work and entertainment categories."""
    work = [0.0] * 24
    entertainment = [0.0] * 24
    total = [0.0] * 24

    for session in sessions:
        category_key = str(session.get("category_key", "") or "")
        is_work = category_key in WORK_KEYS
        is_entertainment = category_key in ENTERTAINMENT_KEYS

        start_dt = _parse_dt(session.get("start_time", ""))
        end_dt = _parse_dt(session.get("end_time", ""))
        effective_seconds = float(session.get("effective_seconds", 0) or 0)
        if effective_seconds <= 0 or start_dt is None or end_dt is None:
            continue

        total_span = (end_dt - start_dt).total_seconds()
        if total_span <= 0:
            contrib = effective_seconds / 60.0
            h = start_dt.hour
            total[h] += contrib
            if is_work:
                work[h] += contrib
            elif is_entertainment:
                entertainment[h] += contrib
            continue

        current = start_dt
        while current < end_dt:
            hour = current.hour
            next_hour = current.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            segment_end = min(end_dt, next_hour)
            seg_sec = (segment_end - current).total_seconds()
            ratio = seg_sec / total_span
            contrib = (effective_seconds * ratio) / 60.0
            total[hour] += contrib
            if is_work:
                work[hour] += contrib
            elif is_entertainment:
                entertainment[hour] += contrib
            current = segment_end

    return {
        "work": [round(v) for v in work],
        "entertainment": [round(v) for v in entertainment],
        "total": [round(v) for v in total],
    }


def build_focus_summary(db_path: str, date_str: str) -> tuple[str, int]:
    blocks = timeline.identify_focus_blocks(timeline.build_timeline(db_path, date_str))
    if blocks:
        best = max(blocks, key=lambda block: block.duration_minutes)
        summary = f"最长专注：{best.start_slot}-{best.end_slot}，{best.duration_minutes}分钟，{best.main_category}"
    else:
        summary = "今日暂未识别到连续专注时段。"
    return summary, database.count_consecutive_days(db_path)


def build_today_insights(
    today: str,
    sessions: list[dict],
    totals: dict,
    distribution_sections: list[dict],
    day_comparison: dict,
) -> dict[str, object]:
    effective_seconds = int((totals or {}).get("effective_seconds", 0) or 0)
    if effective_seconds < 1800 or len(sessions) < 2:
        return {
            "ready": False,
            "message": "数据积累中",
            "hint": "使用一段时间后将生成洞察",
            "cards": [],
        }

    cards: list[dict[str, object]] = []
    longest = _find_longest_session(sessions)
    if longest is not None:
        cards.append(
            {
                "title": "最长专注",
                "icon": "🏆",
                "accent": "#2ecc71",
                "primary": _session_label(longest),
                "secondary": f"{fmt_seconds(_session_seconds(longest))} · {_session_time_range(longest)}",
            }
        )

    best_window = _find_best_state_window(sessions)
    if best_window is not None:
        start_hour, end_hour, minutes = best_window
        cards.append(
            {
                "title": "最佳状态时段",
                "icon": "🕒",
                "accent": "#3b82f6",
                "primary": f"{start_hour:02d}:00 - {end_hour:02d}:00",
                "secondary": f"累计专注 {minutes}分钟",
            }
        )

    busiest = _find_busiest_session_source(sessions)
    if busiest is not None:
        label, count = busiest
        cards.append(
            {
                "title": "最大干扰源",
                "icon": "⚠",
                "accent": "#f59e0b",
                "primary": label,
                "secondary": f"会话 {count} 次",
            }
        )

    cards.append(_build_today_advice_card(totals, sessions, distribution_sections, day_comparison))
    return {"ready": True, "cards": cards}


def _find_longest_session(sessions: list[dict]) -> dict | None:
    valid_sessions = [session for session in sessions if _session_seconds(session) > 0]
    if not valid_sessions:
        return None
    return max(valid_sessions, key=lambda session: (_session_seconds(session), str(session.get("end_time", "") or "")))


def _find_best_state_window(sessions: list[dict]) -> tuple[int, int, int] | None:
    hourly_minutes = build_hourly_series(sessions)
    if not any(hourly_minutes):
        return None
    best_start = 0
    best_minutes = -1
    for start_hour in range(23):
        window_minutes = hourly_minutes[start_hour] + hourly_minutes[start_hour + 1]
        if window_minutes > best_minutes:
            best_minutes = window_minutes
            best_start = start_hour
    return best_start, min(24, best_start + 2), int(best_minutes)


def _find_busiest_session_source(sessions: list[dict]) -> tuple[str, int] | None:
    counts: dict[str, int] = {}
    for session in sessions:
        if _session_seconds(session) < 60:
            continue
        label = _session_source_label(session)
        counts[label] = counts.get(label, 0) + 1
    if not counts:
        return None
    return max(counts.items(), key=lambda item: (item[1], item[0]))


def _build_today_advice_card(
    totals: dict,
    sessions: list[dict],
    distribution_sections: list[dict],
    day_comparison: dict,
) -> dict[str, object]:
    morning_minutes = 0
    afternoon_minutes = 0
    work_seconds = 0
    entertainment_seconds = 0
    for session in sessions:
        seconds = _session_seconds(session)
        if seconds <= 0:
            continue
        start_dt = _parse_dt(str(session.get("start_time", "") or ""))
        if start_dt is not None:
            if start_dt.hour < 12:
                morning_minutes += seconds // 60
            else:
                afternoon_minutes += seconds // 60
        category_key = str(session.get("category_key", "") or "")
        if category_key in WORK_KEYS or category_key == "work":
            work_seconds += seconds
        elif category_key in {"video", "gaming", "entertainment"}:
            entertainment_seconds += seconds

    if afternoon_minutes >= max(morning_minutes * 1.15, morning_minutes + 15):
        primary = "下午专注度明显高于上午"
        secondary = "建议将高优先级任务安排在 14:00 后"
    elif morning_minutes > afternoon_minutes * 1.15:
        primary = "上午更适合深度工作"
        secondary = "可优先把需要专注的任务放到早上完成"
    elif entertainment_seconds > work_seconds:
        primary = "今天娱乐时间略多"
        secondary = "可缩短碎片娱乐，给深度工作预留连续片段"
    else:
        primary = "今日节奏比较平衡"
        secondary = "继续保持环境稳定，把相同类型任务合并处理"

    if len(secondary) > 28:
        secondary = secondary[:27] + "…"
    return {
        "title": "今日建议",
        "icon": "💡",
        "accent": "#a855f7",
        "primary": primary,
        "secondary": secondary,
    }


def _session_seconds(session: dict) -> int:
    seconds = session.get("effective_seconds", 0) or session.get("duration_seconds", 0) or 0
    return int(seconds)


def _session_label(session: dict) -> str:
    for key in ("normalized_title", "window_title", "process_name"):
        value = str(session.get(key, "") or "").strip()
        if value:
            return value.removesuffix(".exe").removesuffix(".EXE")
    return "未知应用"


def _session_source_label(session: dict) -> str:
    label = _session_label(session)
    if label:
        return label
    process_name = str(session.get("process_name", "") or "").strip()
    return process_name.removesuffix(".exe").removesuffix(".EXE") or "未知应用"


def _session_time_range(session: dict) -> str:
    start = str(session.get("start_time", "") or "")
    end = str(session.get("end_time", "") or "")
    start_short = start[11:16] if len(start) >= 16 else start
    end_short = end[11:16] if len(end) >= 16 else end
    return f"{start_short} - {end_short}".strip()


def load_today_snapshot(db_path: str, resolve_display) -> dict[str, object]:
    today_str = datetime.now().strftime("%Y-%m-%d")
    stats = database.query_date_stats(db_path, today_str)
    totals = stats.get("totals", {})
    effective_seconds = int(totals.get("effective_seconds", 0) or 0)
    idle_seconds = int(totals.get("idle_seconds", 0) or 0)
    total_seconds = effective_seconds + idle_seconds
    active_ratio = int(round((effective_seconds / total_seconds) * 100)) if total_seconds else 0

    yesterday_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    yesterday_stats = database.query_date_stats(db_path, yesterday_str)
    sessions = database.query_today_sessions(db_path, today_str)
    yesterday_sessions = database.query_today_sessions(db_path, yesterday_str)

    today_date = date.today()
    seven_day_dates = _rolling_date_strings(today_date, 7)
    thirty_day_dates = _rolling_date_strings(today_date, 30)
    thirty_day_stats = database.query_date_range_stats(
        db_path,
        thirty_day_dates,
    )
    seven_day_sessions = [
        database.query_today_sessions(db_path, day_str)
        for day_str in seven_day_dates
    ]

    focus_summary, consecutive_days = build_focus_summary(db_path, today_str)
    distribution_sections = build_distribution_sections(stats, effective_seconds)
    day_comparison = build_day_over_day_comparison(stats, yesterday_stats)
    split_today = build_hourly_series_split(sessions)
    split_yesterday = build_hourly_series_split(yesterday_sessions)
    return {
        "today": today_str,
        "stats": stats,
        "totals": {
            "effective_seconds": effective_seconds,
            "idle_seconds": idle_seconds,
            "total_seconds": total_seconds,
            "active_ratio": active_ratio,
        },
        "distribution_sections": distribution_sections,
        "day_comparison": day_comparison,
        "sessions": sessions,
        "focus_summary": focus_summary,
        "consecutive_days": consecutive_days,
        "top_app_rows": build_top_app_rows(stats, resolve_display),
        "trend": {
            "today": split_today["total"],
            "today_work": split_today["work"],
            "today_entertainment": split_today["entertainment"],
            "yesterday": build_hourly_series(yesterday_sessions),
            "yesterday_work": split_yesterday["work"],
            "yesterday_entertainment": split_yesterday["entertainment"],
            "seven_days": [
                build_hourly_series(day_sessions)
                for day_sessions in seven_day_sessions
            ],
            "seven_day_labels": seven_day_dates,
            "thirty_days": [
                round((item.get("effective_seconds", 0) or 0) / 3600.0, 1)
                for item in thirty_day_stats.get("daily", [])
            ],
        },
    }


def _parse_dt(timestamp: str) -> datetime | None:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
