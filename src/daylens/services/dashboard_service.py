"""Build homepage view data outside the Qt page layer."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import html
import logging
import unicodedata

from .. import database, timeline
from ..utils import fmt_seconds, parse_nonnegative_int
from .insights_service import select_primary_insight
from .trusted_metrics_service import (
    REASON_FORMAT_INVALID,
    REASON_TIMING_ANOMALY_ABOVE_LIMIT,
    assess_range,
    compare_ranges,
)

WORK_KEYS = {"ai_tools", "coding", "office", "reading", "creative"}
ENTERTAINMENT_KEYS = {"video", "gaming"}
LOGGER = logging.getLogger(__name__)
THIRTY_DAY_METRIC_BREAK_NOTICE = (
    "计量口径已变化，历史参与趋势暂不可比"
)


def _rolling_date_strings(end_date: date, days: int) -> list[str]:
    """Return an inclusive rolling window ordered from oldest to newest."""
    count = max(0, int(days))
    return [
        (end_date - timedelta(days=offset)).strftime("%Y-%m-%d")
        for offset in reversed(range(count))
    ]


def _sessions_for_date(sessions: list[dict], date_str: str) -> list[dict]:
    return [
        session
        for session in sessions
        if str(session.get("date", "") or "") == date_str
    ]


_SESSION_SECONDS_FIELDS = (
    "duration_seconds",
    "effective_seconds",
    "engaged_seconds",
    "passive_seconds",
    "idle_seconds",
)


def _sanitize_session(session: dict) -> dict | None:
    sanitized = dict(session)
    for field in _SESSION_SECONDS_FIELDS:
        parsed = parse_nonnegative_int(session.get(field))
        if parsed is None:
            return None
        sanitized[field] = parsed
    if _session_interval(sanitized) is None:
        return None
    return sanitized


def _sanitize_sessions(sessions: list[dict]) -> tuple[list[dict], set[str]]:
    sanitized: list[dict] = []
    malformed_dates: set[str] = set()
    for session in sessions:
        clean = _sanitize_session(session)
        if clean is None:
            malformed_dates.add(str(session.get("date", "") or ""))
            continue
        sanitized.append(clean)
    return sanitized, malformed_dates


def _apply_session_payload_health(
    trust: dict[str, object],
    malformed_dates: set[str],
    expected_dates: list[str],
) -> dict[str, object]:
    if not malformed_dates.intersection(expected_dates):
        return trust
    reasons = [str(reason) for reason in trust.get("reasons", [])]
    if REASON_TIMING_ANOMALY_ABOVE_LIMIT not in reasons:
        reasons.append(REASON_TIMING_ANOMALY_ABOVE_LIMIT)
    return {
        **trust,
        "level": "low",
        "reasons": reasons,
        "category_comparable": False,
    }


def _engaged_seconds_by_hour(sessions: list[dict]) -> list[float]:
    hourly = [0.0] * 24
    for session in sessions:
        if str(session.get("category_key", "") or "") not in WORK_KEYS:
            continue
        engaged = parse_nonnegative_int(session.get("engaged_seconds"))
        start_dt = _parse_dt(str(session.get("start_time", "") or ""))
        end_dt = _parse_dt(str(session.get("end_time", "") or ""))
        if engaged is None or engaged <= 0 or start_dt is None or end_dt is None:
            continue
        span = (end_dt - start_dt).total_seconds()
        if span <= 0:
            hourly[start_dt.hour] += engaged
            continue
        current = start_dt
        while current < end_dt:
            next_hour = (
                current.replace(minute=0, second=0, microsecond=0)
                + timedelta(hours=1)
            )
            segment_end = min(end_dt, next_hour)
            segment_seconds = (segment_end - current).total_seconds()
            hourly[current.hour] += engaged * segment_seconds / span
            current = segment_end
    return hourly


def _build_best_window_section(
    sessions: list[dict],
    date_range: list[str],
) -> dict[str, object]:
    hourly = _engaged_seconds_by_hour(sessions)
    start_hour = max(
        range(23),
        key=lambda hour: hourly[hour] + hourly[hour + 1],
    )
    workday_count = len(
        {
            str(session.get("date", "") or "")
            for session in sessions
            if str(session.get("category_key", "") or "") in WORK_KEYS
            and (parse_nonnegative_int(session.get("engaged_seconds")) or 0) > 0
        }
    )
    return {
        "date_range": list(date_range),
        "workday_count": workday_count,
        "start_hour": start_hour,
        "end_hour": start_hour + 2,
        "window_work_engaged_seconds": int(
            round(hourly[start_hour] + hourly[start_hour + 1])
        ),
        "total_work_engaged_seconds": int(round(sum(hourly))),
    }


def _session_interval(session: dict) -> tuple[datetime, datetime] | None:
    start_dt = _parse_dt(str(session.get("start_time", "") or ""))
    end_dt = _parse_dt(str(session.get("end_time", "") or ""))
    if start_dt is None or end_dt is None or end_dt < start_dt:
        return None
    return start_dt, end_dt


def _interval_gap_seconds(
    left: tuple[datetime, datetime],
    right: tuple[datetime, datetime],
) -> float:
    if left[1] < right[0]:
        return (right[0] - left[1]).total_seconds()
    if right[1] < left[0]:
        return (left[0] - right[1]).total_seconds()
    return 0.0


def _build_interruptions_section(
    sessions: list[dict],
    date_range: list[str],
    classification_comparable: bool,
) -> dict[str, object]:
    work_intervals = [
        interval
        for session in sessions
        if str(session.get("category_key", "") or "") in WORK_KEYS
        if (interval := _session_interval(session)) is not None
    ]
    count = 0
    seen_events: set[tuple[str, ...]] = set()
    for session in sessions:
        category_key = str(session.get("category_key", "") or "")
        if category_key != "social" and category_key not in ENTERTAINMENT_KEYS:
            continue
        event_identity = _session_event_identity(session)
        if event_identity in seen_events:
            continue
        seen_events.add(event_identity)
        interval = _session_interval(session)
        if interval is None:
            continue
        if any(
            interval[0].date() == work_interval[0].date()
            and _interval_gap_seconds(interval, work_interval) <= 15 * 60
            for work_interval in work_intervals
        ):
            count += 1
    return {
        "date_range": list(date_range),
        "count": count,
        "window_minutes": 15,
        "classification_comparable": bool(classification_comparable),
    }


def _session_event_identity(session: dict) -> tuple[str, ...]:
    session_id = str(session.get("session_id", "") or "").strip()
    if session_id:
        return ("session_id", session_id)
    return (
        "fallback",
        str(session.get("date", "") or ""),
        str(session.get("start_time", "") or ""),
        str(session.get("end_time", "") or ""),
        str(session.get("process_name", "") or ""),
        str(session.get("category_key", "") or ""),
        str(session.get("normalized_title", "") or ""),
        str(session.get("window_title", "") or ""),
    )


def _strip_executable_suffix(value: str) -> str:
    return value[:-4] if value.casefold().endswith(".exe") else value


def _safe_tool_text(source: str) -> str | None:
    label = unicodedata.normalize("NFKC", str(source or "")).strip()
    label = _strip_executable_suffix(label)
    if not label or len(label) > 64 or label.strip() != label:
        return None
    if any(unicodedata.category(char).startswith("C") for char in label):
        return None
    decoded = label
    for _ in range(3):
        decoded_next = html.unescape(decoded)
        if decoded_next == decoded:
            break
        decoded = decoded_next
    if "<" in decoded and ">" in decoded:
        return None
    return label


def _stable_tool_identity(
    session: dict,
    resolve_display=None,
) -> tuple[str, str] | None:
    process_name = unicodedata.normalize(
        "NFKC",
        str(session.get("process_name", "") or "").strip(),
    )
    process_label = _safe_tool_text(process_name)
    if process_label is None:
        return None
    identity = process_label.casefold()
    display_label = None
    if resolve_display is not None:
        try:
            display_label = _safe_tool_text(
                str(resolve_display(process_name, []) or "")
            )
        except Exception:
            display_label = None
    return identity, display_label or process_label


def _build_workflow_section(
    sessions: list[dict],
    date_range: list[str],
    resolve_display=None,
) -> dict[str, object]:
    by_date: dict[str, list[dict]] = {}
    for session in sessions:
        by_date.setdefault(str(session.get("date", "") or ""), []).append(session)

    tools: list[str] = []
    seen_tools: set[str] = set()
    switch_count = 0
    non_work_interruptions = 0
    for date_str in sorted(by_date):
        ordered = sorted(
            by_date[date_str],
            key=lambda session: (
                str(session.get("start_time", "") or ""),
                str(session.get("end_time", "") or ""),
            ),
        )
        for session in ordered:
            if str(session.get("category_key", "") or "") not in WORK_KEYS:
                continue
            tool = _stable_tool_identity(session, resolve_display)
            if tool is None:
                continue
            identity, display_label = tool
            if identity not in seen_tools:
                seen_tools.add(identity)
                tools.append(display_label)

        for previous, current in zip(ordered, ordered[1:]):
            if (
                str(previous.get("category_key", "") or "") in WORK_KEYS
                and str(current.get("category_key", "") or "") in WORK_KEYS
            ):
                previous_tool = _stable_tool_identity(
                    previous,
                    resolve_display,
                )
                current_tool = _stable_tool_identity(
                    current,
                    resolve_display,
                )
                if (
                    previous_tool
                    and current_tool
                    and previous_tool[0] != current_tool[0]
                ):
                    switch_count += 1

        for index, session in enumerate(ordered):
            if str(session.get("category_key", "") or "") in WORK_KEYS:
                continue
            has_work_before = any(
                str(item.get("category_key", "") or "") in WORK_KEYS
                for item in ordered[:index]
            )
            has_work_after = any(
                str(item.get("category_key", "") or "") in WORK_KEYS
                for item in ordered[index + 1 :]
            )
            if has_work_before and has_work_after:
                non_work_interruptions += 1

    return {
        "date_range": list(date_range),
        "tool_count": len(tools),
        "switch_count": switch_count,
        "non_work_interruptions": non_work_interruptions,
        "tools": tools,
    }


def _fallback_trust() -> dict[str, object]:
    return {
        "level": "low",
        "reasons": [REASON_FORMAT_INVALID],
        "coverage_ratio": 0.0,
        "legacy_ratio": 1.0,
        "anomaly_ratio": 0.0,
        "metric_versions": [],
        "classification_versions": [],
        "category_comparable": False,
    }


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
            seconds = parse_nonnegative_int(detail.get("effective_seconds")) or 0
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
        seconds = parse_nonnegative_int(item.get("effective_seconds")) or 0
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
        (parse_nonnegative_int(effective_seconds) or 0)
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
        seconds = parse_nonnegative_int(item.get("effective_seconds")) or 0
        bucket = merged.setdefault(display_name, {"process_name": process_name, "display_name": display_name, "seconds": 0})
        bucket["seconds"] = int(bucket["seconds"]) + seconds
    return sorted(merged.values(), key=lambda item: -int(item["seconds"]))[:9]


def build_hourly_series(sessions: list[dict]) -> list[int]:
    hour_minutes = [0.0] * 24
    for session in sessions:
        start_dt = _parse_dt(session.get("start_time", ""))
        end_dt = _parse_dt(session.get("end_time", ""))
        effective_seconds = parse_nonnegative_int(session.get("effective_seconds"))
        if (
            effective_seconds is None
            or effective_seconds <= 0
            or start_dt is None
            or end_dt is None
        ):
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
    work_seconds = [0] * 24
    entertainment = [0.0] * 24
    total = [0.0] * 24

    for session in sessions:
        category_key = str(session.get("category_key", "") or "")
        is_work = category_key in WORK_KEYS
        is_entertainment = category_key in ENTERTAINMENT_KEYS

        start_dt = _parse_dt(session.get("start_time", ""))
        end_dt = _parse_dt(session.get("end_time", ""))
        effective_seconds = parse_nonnegative_int(session.get("effective_seconds"))
        engaged_seconds = (
            parse_nonnegative_int(session.get("engaged_seconds")) or 0
        )
        if (
            effective_seconds is None
            or effective_seconds <= 0
            or start_dt is None
            or end_dt is None
        ):
            continue

        total_span = (end_dt - start_dt).total_seconds()
        if total_span < 0:
            continue
        if is_work:
            engaged_by_hour = timeline.allocate_seconds_to_hour_buckets(
                start_dt,
                end_dt,
                engaged_seconds,
            )
            work_seconds = [
                current + added
                for current, added in zip(work_seconds, engaged_by_hour)
            ]
        if total_span <= 0:
            contrib = effective_seconds / 60.0
            h = start_dt.hour
            total[h] += contrib
            if is_entertainment:
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
            if is_entertainment:
                entertainment[hour] += contrib
            current = segment_end

    return {
        "work": timeline.seconds_buckets_to_minutes(work_seconds),
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
    try:
        consecutive_days = database.count_consecutive_days(db_path)
    except Exception:
        LOGGER.exception("Failed to count consecutive focus days")
        consecutive_days = 0
    return summary, consecutive_days


def build_today_insights(
    today: str,
    sessions: list[dict],
    totals: dict,
    distribution_sections: list[dict],
    day_comparison: dict,
) -> dict[str, object]:
    effective_seconds = (
        parse_nonnegative_int((totals or {}).get("effective_seconds")) or 0
    )
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
    effective = parse_nonnegative_int(session.get("effective_seconds"))
    if effective is not None and effective > 0:
        return effective
    return parse_nonnegative_int(session.get("duration_seconds")) or 0


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


def _day_has_metric_data(item: dict) -> bool:
    for field in (
        "session_count",
        "legacy_log_sample_count",
        "total_samples",
        "effective_seconds",
        "engaged_seconds",
        "passive_seconds",
        "idle_seconds",
    ):
        if field not in item:
            continue
        parsed = parse_nonnegative_int(item.get(field))
        if parsed is None:
            return True
        if parsed > 0:
            return True
    return bool(item.get("dates_with_data") or item.get("metric_versions"))


def _day_is_attention_v1_only(item: dict) -> bool:
    metric_versions = {
        str(version or "")
        for version in (item.get("metric_versions") or [])
        if str(version or "")
    }
    return (
        (parse_nonnegative_int(item.get("session_count")) or 0) > 0
        and (parse_nonnegative_int(item.get("legacy_session_count")) or 0)
        == 0
        and (
            parse_nonnegative_int(item.get("legacy_log_sample_count")) or 0
        )
        == 0
        and not bool(item.get("legacy_granularity_unknown", False))
        and metric_versions == {"attention-v1"}
    )


def _build_thirty_day_trend(
    daily_rows: list[dict],
) -> list[float | None]:
    points: list[float | None] = []
    for item in daily_rows:
        if not _day_has_metric_data(item):
            points.append(0.0)
        elif not _day_is_attention_v1_only(item):
            points.append(None)
        else:
            seconds = parse_nonnegative_int(item.get("engaged_seconds")) or 0
            points.append(round(seconds / 3600.0, 1))
    return points


def _has_thirty_day_classification_break(daily_rows: list[dict]) -> bool:
    versions = {
        str(version or "")
        for item in daily_rows
        if _day_has_metric_data(item)
        for version in (item.get("classification_versions") or [])
        if str(version or "")
    }
    return len(versions) > 1


def load_today_snapshot(db_path: str, resolve_display) -> dict[str, object]:
    captured_now = datetime.now()
    today_date = captured_now.date()
    today_str = today_date.strftime("%Y-%m-%d")
    yesterday_str = (captured_now - timedelta(days=1)).strftime("%Y-%m-%d")
    seven_day_dates = _rolling_date_strings(today_date, 7)
    fourteen_day_dates = _rolling_date_strings(today_date, 14)
    prior_seven_day_dates = fourteen_day_dates[:7]
    thirty_day_dates = _rolling_date_strings(today_date, 30)

    stats = database.query_date_stats(db_path, today_str)
    yesterday_stats = database.query_date_stats(db_path, yesterday_str)
    totals = stats.get("totals", {})
    effective_seconds = parse_nonnegative_int(totals.get("effective_seconds")) or 0
    engaged_seconds = parse_nonnegative_int(totals.get("engaged_seconds")) or 0
    passive_seconds = parse_nonnegative_int(totals.get("passive_seconds")) or 0
    idle_seconds = parse_nonnegative_int(totals.get("idle_seconds")) or 0
    total_seconds = effective_seconds + idle_seconds
    attention_total = engaged_seconds + passive_seconds + idle_seconds
    active_ratio = (
        int(round((engaged_seconds / attention_total) * 100))
        if attention_total
        else 0
    )
    passive_ratio = (
        int(round((passive_seconds / attention_total) * 100))
        if attention_total
        else 0
    )
    idle_ratio = max(0, 100 - active_ratio - passive_ratio) if attention_total else 0

    trusted_calculation_failed = False
    try:
        thirty_day_stats = database.query_date_range_stats(
            db_path,
            thirty_day_dates,
        )
        thirty_day_daily = thirty_day_stats.get("daily", [])
    except Exception:
        LOGGER.exception("Failed to read dashboard thirty-day range")
        thirty_day_stats = {"daily": []}
        thirty_day_daily = []
        trusted_calculation_failed = True
    try:
        thirty_day_trend = _build_thirty_day_trend(thirty_day_daily)
    except Exception:
        LOGGER.exception("Failed to build dashboard thirty-day trend")
        thirty_day_trend = []
    thirty_day_metric_break = any(
        point is None for point in thirty_day_trend
    )
    thirty_day_classification_break = (
        _has_thirty_day_classification_break(thirty_day_daily)
    )
    try:
        raw_fourteen_day_sessions = database.query_sessions_for_dates(
            db_path,
            fourteen_day_dates,
        )
        fourteen_day_sessions, malformed_session_dates = _sanitize_sessions(
            raw_fourteen_day_sessions
        )
        sessions = _sessions_for_date(fourteen_day_sessions, today_str)
        yesterday_sessions = _sessions_for_date(
            fourteen_day_sessions,
            yesterday_str,
        )
        seven_day_sessions = [
            _sessions_for_date(fourteen_day_sessions, day_str)
            for day_str in seven_day_dates
        ]
    except Exception:
        LOGGER.exception("Failed to read dashboard session range")
        trusted_calculation_failed = True
        fourteen_day_sessions = []
        malformed_session_dates = set()
        fallback_sessions, fallback_malformed_dates = _sanitize_sessions(
            [
                *database.query_today_sessions(db_path, today_str),
                *database.query_today_sessions(db_path, yesterday_str),
            ]
        )
        malformed_session_dates.update(fallback_malformed_dates)
        sessions = _sessions_for_date(fallback_sessions, today_str)
        yesterday_sessions = _sessions_for_date(fallback_sessions, yesterday_str)
        seven_day_sessions = [[] for _ in seven_day_dates]

    focus_summary, consecutive_days = build_focus_summary(db_path, today_str)
    distribution_sections = build_distribution_sections(stats, effective_seconds)
    day_comparison = build_day_over_day_comparison(stats, yesterday_stats)
    split_today = build_hourly_series_split(sessions)
    split_yesterday = build_hourly_series_split(yesterday_sessions)
    trust = _fallback_trust()
    comparison = {
        "comparable": False,
        "category_comparable": False,
        "reason": "数据质量不足，无法比较",
    }
    insight = None
    insight_payload: dict[str, object] | None = None
    if not trusted_calculation_failed:
        try:
            fourteen_day_summary = database.summarize_daily_trusted_metrics(
                thirty_day_daily,
                fourteen_day_dates,
            )
            recent_summary = database.summarize_daily_trusted_metrics(
                thirty_day_daily,
                seven_day_dates,
            )
            prior_summary = database.summarize_daily_trusted_metrics(
                thirty_day_daily,
                prior_seven_day_dates,
            )
            trust = assess_range(
                fourteen_day_summary,
                fourteen_day_dates,
            )
            recent_trust = assess_range(
                recent_summary,
                seven_day_dates,
            )
            prior_trust = assess_range(
                prior_summary,
                prior_seven_day_dates,
            )
            trust = _apply_session_payload_health(
                trust,
                malformed_session_dates,
                fourteen_day_dates,
            )
            recent_trust = _apply_session_payload_health(
                recent_trust,
                malformed_session_dates,
                seven_day_dates,
            )
            prior_trust = _apply_session_payload_health(
                prior_trust,
                malformed_session_dates,
                prior_seven_day_dates,
            )
            comparison = compare_ranges(prior_trust, recent_trust)
            category_comparable = bool(
                trust.get("category_comparable", False)
                and comparison.get("category_comparable", False)
            )
            recent_date_set = set(seven_day_dates)
            recent_sessions = [
                session
                for session in fourteen_day_sessions
                if str(session.get("date", "") or "") in recent_date_set
            ]
            insight_payload = {
                "date_range": [fourteen_day_dates[0], fourteen_day_dates[-1]],
                "trust": trust,
                "best_window": _build_best_window_section(
                    fourteen_day_sessions,
                    [fourteen_day_dates[0], fourteen_day_dates[-1]],
                ),
                "interruptions": _build_interruptions_section(
                    recent_sessions,
                    [seven_day_dates[0], seven_day_dates[-1]],
                    category_comparable,
                ),
                "trend": {
                    "prior_range": [
                        prior_seven_day_dates[0],
                        prior_seven_day_dates[-1],
                    ],
                    "recent_range": [seven_day_dates[0], seven_day_dates[-1]],
                    "recent_work_engaged_seconds": int(
                        recent_summary.get("work_engaged_seconds", 0)
                        or 0
                    ),
                    "prior_work_engaged_seconds": int(
                        prior_summary.get("work_engaged_seconds", 0)
                        or 0
                    ),
                    "comparison_comparable": bool(
                        comparison.get("comparable", False)
                    ),
                    "category_comparable": category_comparable,
                },
                "workflow": _build_workflow_section(
                    recent_sessions,
                    [seven_day_dates[0], seven_day_dates[-1]],
                    resolve_display,
                ),
            }
        except Exception:
            LOGGER.exception("Failed to build trusted dashboard metrics")
            trusted_calculation_failed = True
            trust = _fallback_trust()
            comparison = {
                "comparable": False,
                "category_comparable": False,
                "reason": "数据质量不足，无法比较",
            }

    if not trusted_calculation_failed and insight_payload is not None:
        try:
            insight = select_primary_insight(insight_payload)
        except Exception:
            LOGGER.exception("Failed to build dashboard insight")
    return {
        "today": today_str,
        "stats": stats,
        "totals": {
            "effective_seconds": effective_seconds,
            "engaged_seconds": engaged_seconds,
            "passive_seconds": passive_seconds,
            "idle_seconds": idle_seconds,
            "total_seconds": total_seconds,
            "active_ratio": active_ratio,
            "passive_ratio": passive_ratio,
            "idle_ratio": idle_ratio,
            "primary_metric": "engaged",
        },
        "distribution_sections": distribution_sections,
        "day_comparison": day_comparison,
        "sessions": sessions,
        "focus_summary": focus_summary,
        "consecutive_days": consecutive_days,
        "top_app_rows": build_top_app_rows(stats, resolve_display),
        "trust": trust,
        "comparison": comparison,
        "insight": insight,
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
            "thirty_days": thirty_day_trend,
            "thirty_day_metric": "engaged",
            "thirty_day_metric_break": thirty_day_metric_break,
            "thirty_day_classification_break": (
                thirty_day_classification_break
            ),
            "thirty_day_notice": (
                THIRTY_DAY_METRIC_BREAK_NOTICE
                if thirty_day_metric_break
                else ""
            ),
        },
    }


def _parse_dt(timestamp: str) -> datetime | None:
    try:
        return datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None
