"""Build homepage view data outside the Qt page layer."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import html
import logging
import math
from statistics import median
import unicodedata

from .. import database, timeline
from ..repositories.stats_repository import session_row_is_anomalous
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

RHYTHM_CONTINUITY_GAP_SECONDS = 30
RHYTHM_HISTORY_START_DATE = date(2026, 8, 13)


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


def _allocate_seconds_to_half_hours(
    start_dt: datetime,
    end_dt: datetime,
    seconds: int,
) -> list[int]:
    buckets = [0] * 48
    if seconds <= 0 or end_dt < start_dt:
        return buckets
    if end_dt == start_dt:
        buckets[start_dt.hour * 2 + (1 if start_dt.minute >= 30 else 0)] = seconds
        return buckets
    span = (end_dt - start_dt).total_seconds()
    pieces: list[tuple[int, float]] = []
    current = start_dt
    while current < end_dt:
        slot_start = current.replace(
            minute=30 if current.minute >= 30 else 0,
            second=0,
            microsecond=0,
        )
        slot_end = slot_start + timedelta(minutes=30)
        segment_end = min(end_dt, slot_end)
        slot_index = current.hour * 2 + (1 if current.minute >= 30 else 0)
        pieces.append((slot_index, seconds * (segment_end - current).total_seconds() / span))
        current = segment_end
    floors = [(index, math.floor(value), value - math.floor(value)) for index, value in pieces]
    remainder = seconds - sum(value for _, value, _ in floors)
    for position, (index, value, _fraction) in enumerate(
        sorted(floors, key=lambda item: (-item[2], item[0]))
    ):
        buckets[index] += value + (1 if position < remainder else 0)
    return buckets


def build_work_engaged_half_hours(
    sessions: list[dict],
    date_str: str,
    *,
    through_time=None,
) -> list[int]:
    """Allocate work-learning engaged seconds into 48 exact half-hour buckets."""
    buckets = [0] * 48
    for session in sessions:
        if str(session.get("date", "") or "") != date_str:
            continue
        if str(session.get("category_key", "") or "") not in WORK_KEYS:
            continue
        engaged = parse_nonnegative_int(session.get("engaged_seconds"))
        interval = _session_interval(session)
        if engaged is None or engaged <= 0 or interval is None:
            continue
        try:
            requested_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except (TypeError, ValueError, OverflowError):
            continue
        day_start = datetime.combine(requested_date, datetime.min.time())
        day_end = day_start + timedelta(days=1)
        clipped_start = max(interval[0], day_start)
        clipped_end = min(interval[1], day_end)
        if through_time is not None:
            clipped_end = min(
                clipped_end,
                datetime.combine(requested_date, through_time),
            )
        full_span = (interval[1] - interval[0]).total_seconds()
        clipped_span = (clipped_end - clipped_start).total_seconds()
        if full_span > 0 and clipped_span > 0:
            clipped_engaged = round(engaged * clipped_span / full_span)
        elif clipped_span == 0 and interval[0] == interval[1]:
            clipped_engaged = engaged
        else:
            continue
        allocated = _allocate_seconds_to_half_hours(
            clipped_start,
            clipped_end,
            clipped_engaged,
        )
        buckets = [current + added for current, added in zip(buckets, allocated)]
    return buckets


def _cumulative(values: list[int]) -> list[int]:
    total = 0
    result: list[int] = []
    for value in values:
        total += int(value)
        result.append(total)
    return result


def _percentile(values: list[int], quantile: float) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return round(ordered[lower] * (1 - fraction) + ordered[upper] * fraction)


def _work_intervals(sessions: list[dict], date_str: str) -> list[tuple[datetime, datetime, int]]:
    intervals: list[tuple[datetime, datetime, int]] = []
    for session in sessions:
        if str(session.get("date", "") or "") != date_str:
            continue
        if str(session.get("category_key", "") or "") not in WORK_KEYS:
            continue
        engaged = parse_nonnegative_int(session.get("engaged_seconds")) or 0
        interval = _session_interval(session)
        if engaged > 0 and interval is not None:
            intervals.append((interval[0], interval[1], engaged))
    return sorted(intervals, key=lambda item: (item[0], item[1]))


def _rhythm_day_metrics(sessions: list[dict], date_str: str) -> dict[str, int | str | None]:
    intervals = _work_intervals(sessions, date_str)
    if not intervals:
        return {"first_start": None, "longest_seconds": 0, "interruptions": 0}
    groups: list[list[tuple[datetime, datetime, int]]] = []
    for interval in intervals:
        if not groups or (interval[0] - groups[-1][-1][1]).total_seconds() > RHYTHM_CONTINUITY_GAP_SECONDS:
            groups.append([interval])
        else:
            groups[-1].append(interval)
    longest = max(sum(item[2] for item in group) for group in groups)
    interruption = _build_interruptions_section(
        _sessions_for_date(sessions, date_str),
        [date_str],
        True,
    )["count"]
    return {
        "first_start": intervals[0][0].strftime("%H:%M"),
        "longest_seconds": longest,
        "interruptions": int(interruption),
    }


def _duration_short(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分钟"


def _delta_text(delta_seconds: int, *, positive_word: str = "多", negative_word: str = "少") -> str:
    if abs(delta_seconds) < 60:
        return "与平时接近"
    word = positive_word if delta_seconds > 0 else negative_word
    return f"比平时{word}{_duration_short(abs(delta_seconds))}"


def _count_delta_text(delta: int) -> str:
    if delta == 0:
        return "与平时接近"
    return f"比平时{'多' if delta > 0 else '少'}{abs(delta)}次"


def _daily_row_map(daily_rows: list[dict]) -> dict[str, dict]:
    return {str(row.get("date", "") or ""): row for row in daily_rows}


def _trusted_work_seconds(row: dict | None) -> int | None:
    if row is None or not _day_has_metric_data(row) or not _day_is_attention_v1_only(row):
        return None
    if any(
        (parse_nonnegative_int(row.get(field)) or 0) > 0
        for field in (
            "session_anomaly_count",
            "legacy_log_anomaly_count",
            "anomaly_count",
        )
    ):
        return None
    return parse_nonnegative_int(row.get("work_engaged_seconds"))


def _rhythm_display_value(
    row: dict | None,
    day: date,
    *,
    history_start: date,
) -> tuple[int | None, str]:
    """Return a visible rhythm value without treating legacy data as trusted."""
    if day < history_start or row is None or not _day_has_metric_data(row):
        return None, "missing"
    if any(
        (parse_nonnegative_int(row.get(field)) or 0) > 0
        for field in (
            "session_anomaly_count",
            "legacy_log_anomaly_count",
            "anomaly_count",
        )
    ):
        return None, "missing"
    trusted = _trusted_work_seconds(row)
    if trusted is not None:
        return trusted, "current"
    metric_versions = {
        str(version or "")
        for version in (row.get("metric_versions") or [])
        if str(version or "")
    }
    if "legacy" not in metric_versions and (
        parse_nonnegative_int(row.get("legacy_session_count")) or 0
    ) <= 0:
        return None, "missing"
    legacy_value = parse_nonnegative_int(row.get("work_seconds"))
    if legacy_value is None:
        return None, "missing"
    return legacy_value, "legacy"


def _classification_versions(daily_rows: list[dict]) -> set[str]:
    return {
        str(version or "")
        for row in daily_rows
        if _day_has_metric_data(row)
        for version in (row.get("classification_versions") or [])
        if str(version or "")
    }


def _metric_break(daily_rows: list[dict]) -> bool:
    return any(
        _day_has_metric_data(row) and not _day_is_attention_v1_only(row)
        for row in daily_rows
    )


def build_daily_goals(
    *,
    captured_now: datetime,
    daily_rows: list[dict],
    current_work_seconds: int,
    current_entertainment_seconds: int,
    weekday_entertainment_limit_minutes: int,
    weekend_entertainment_limit_minutes: int,
    query_failed: bool,
) -> dict[str, object]:
    """Build the dashboard's smart work target and entertainment boundary."""
    today = captured_now.date()
    row_map = _daily_row_map(daily_rows)
    same_day_type = lambda day: (day.weekday() < 5) == (today.weekday() < 5)
    samples: list[int] = []
    for offset in range(1, 31):
        candidate = today - timedelta(days=offset)
        if not same_day_type(candidate):
            continue
        value = _trusted_work_seconds(row_map.get(candidate.isoformat()))
        if value is not None:
            samples.append(value)
        if len(samples) == 7:
            break

    metric_break = _metric_break(daily_rows)
    classification_break = len(_classification_versions(daily_rows)) > 1
    comparable = (
        not query_failed
        and not metric_break
        and not classification_break
        and len(samples) >= 3
    )
    target_seconds: int | None = None
    if comparable:
        sample_median = float(median(samples))
        rounded_target = int(math.floor((sample_median + 450) / 900) * 900)
        if rounded_target > 0:
            target_seconds = rounded_target
        else:
            comparable = False

    current_work = parse_nonnegative_int(current_work_seconds) or 0
    remaining = (
        max(0, int(target_seconds) - current_work)
        if target_seconds is not None
        else None
    )
    work_progress = (
        min(100, int(round(current_work * 100 / target_seconds)))
        if target_seconds
        else 0
    )

    configured_minutes = (
        weekday_entertainment_limit_minutes
        if today.weekday() < 5
        else weekend_entertainment_limit_minutes
    )
    parsed_limit = parse_nonnegative_int(configured_minutes)
    if parsed_limit is None or parsed_limit > 720:
        parsed_limit = 0
    limit_seconds = parsed_limit * 60 if parsed_limit else None
    current_entertainment = parse_nonnegative_int(current_entertainment_seconds) or 0
    entertainment_progress = (
        min(100, int(round(current_entertainment * 100 / limit_seconds)))
        if limit_seconds
        else 0
    )
    if limit_seconds is None:
        entertainment_state = "unset"
    elif current_entertainment > limit_seconds:
        entertainment_state = "over"
    elif current_entertainment >= limit_seconds * 0.8:
        entertainment_state = "near"
    else:
        entertainment_state = "within"

    if query_failed:
        status = {"label": "暂不可用", "kind": "unavailable"}
    elif metric_break:
        status = {"label": "口径已变化", "kind": "unavailable"}
    elif classification_break:
        status = {"label": "分类已变化", "kind": "unavailable"}
    elif comparable:
        status = {"label": "智能目标", "kind": "ready"}
    else:
        status = {"label": "数据积累中", "kind": "waiting"}

    if not comparable or target_seconds is None:
        advice = "目标数据积累中，先按自己的节奏继续"
    elif entertainment_state == "over":
        advice = "娱乐已超过今日建议边界，建议先回到计划任务"
    elif current_work >= target_seconds:
        advice = "今日工作参与已达到目标，可以开始收尾"
    elif entertainment_state == "near":
        advice = "娱乐接近今日建议边界，建议先完成一个工作段"
    else:
        advice = "再完成一个25分钟工作段，继续接近今日目标"

    return {
        "version": 1,
        "status": status,
        "work": {
            "current_seconds": current_work,
            "target_seconds": target_seconds,
            "remaining_seconds": remaining,
            "progress_percent": work_progress,
            "sample_count": len(samples),
            "comparable": comparable,
        },
        "entertainment": {
            "current_seconds": current_entertainment,
            "limit_seconds": limit_seconds,
            "progress_percent": entertainment_progress,
            "state": entertainment_state,
        },
        "advice": advice,
    }


def _weekday_label(value: date) -> str:
    return "周" + "一二三四五六日"[value.weekday()]


def _build_today_rhythm(
    captured_now: datetime,
    sessions: list[dict],
    daily_rows: list[dict],
    *,
    query_failed: bool,
) -> dict[str, object]:
    today = captured_now.date()
    today_str = today.isoformat()
    row_map = _daily_row_map(daily_rows)
    has_metric_break = _metric_break(daily_rows)
    has_classification_break = len(_classification_versions(daily_rows)) > 1
    same_day_type = lambda day: (day.weekday() < 5) == (today.weekday() < 5)
    candidates: list[str] = []
    for offset in range(1, 31):
        candidate = today - timedelta(days=offset)
        if not same_day_type(candidate):
            continue
        date_str = candidate.isoformat()
        if _trusted_work_seconds(row_map.get(date_str)) is not None:
            candidates.append(date_str)
        if len(candidates) == 7:
            break
    baseline_allowed = (
        not query_failed
        and not has_metric_break
        and not has_classification_break
        and len(candidates) >= 3
    )
    current = _cumulative(
        build_work_engaged_half_hours(
            sessions,
            today_str,
            through_time=captured_now.time(),
        )
    )
    current_slot = min(47, captured_now.hour * 2 + (1 if captured_now.minute >= 30 else 0))
    current_visible: list[int | None] = [
        value if index <= current_slot else None
        for index, value in enumerate(current)
    ]
    baseline_series = [
        _cumulative(
            build_work_engaged_half_hours(
                sessions,
                date_str,
                through_time=captured_now.time(),
            )
        )
        for date_str in candidates
    ] if baseline_allowed else []
    median_line = [round(median([series[index] for series in baseline_series])) for index in range(48)] if baseline_series else []
    low_line = [_percentile([series[index] for series in baseline_series], 0.25) for index in range(48)] if baseline_series else []
    high_line = [_percentile([series[index] for series in baseline_series], 0.75) for index in range(48)] if baseline_series else []
    if baseline_series:
        median_line = [value if index <= current_slot else None for index, value in enumerate(median_line)]
        low_line = [value if index <= current_slot else None for index, value in enumerate(low_line)]
        high_line = [value if index <= current_slot else None for index, value in enumerate(high_line)]
    current_total = current[current_slot]
    baseline_total = int(median([series[current_slot] for series in baseline_series])) if baseline_series else 0
    metrics_by_date = {
        date_str: _rhythm_day_metrics(sessions, date_str)
        for date_str in [today_str, *candidates]
    }
    metrics = metrics_by_date[today_str]
    first_baselines = [
        value
        for date_str in candidates
        if (value := metrics_by_date[date_str]["first_start"]) is not None
    ]
    longest_baselines = [int(metrics_by_date[date_str]["longest_seconds"]) for date_str in candidates]
    interruption_baselines = [int(metrics_by_date[date_str]["interruptions"]) for date_str in candidates]
    if query_failed:
        status = {"label": "暂不可比较", "kind": "unavailable"}
    elif has_metric_break:
        status = {"label": "口径已变化", "kind": "break"}
    elif has_classification_break:
        status = {"label": "暂不可比较", "kind": "break"}
    elif baseline_allowed:
        status = {"label": f"基线{len(candidates)}天", "kind": "baseline"}
    else:
        status = {"label": "数据积累中", "kind": "waiting"}
    if baseline_allowed:
        conclusion = f"截至{captured_now:%H:%M}，{_delta_text(current_total - baseline_total)}"
    else:
        conclusion = f"截至{captured_now:%H:%M}，已参与{_duration_short(current_total)}"
    first_delta = ""
    if baseline_allowed and metrics["first_start"] and first_baselines:
        def minutes(value: str) -> int:
            hour, minute = value.split(":")
            return int(hour) * 60 + int(minute)
        first_diff = minutes(str(metrics["first_start"])) - round(median([minutes(str(value)) for value in first_baselines]))
        first_delta = "与平时接近" if abs(first_diff) < 1 else f"比平时{'晚' if first_diff > 0 else '早'}{abs(first_diff)}分钟"
    return {
        "title": "今日工作节奏",
        "date_range": [today_str, today_str],
        "status": status,
        "conclusion": conclusion,
        "comparison": {
            "comparable": baseline_allowed,
            "sample_count": len(candidates) if baseline_allowed else 0,
            "delta_seconds": current_total - baseline_total if baseline_allowed else None,
        },
        "chart": {
            "kind": "cumulative",
            "labels": [f"{index // 2:02d}:{(index % 2) * 30:02d}" for index in range(48)],
            "current": current_visible,
            "baseline_median": median_line,
            "baseline_low": low_line,
            "baseline_high": high_line,
        },
        "metrics": [
            {"label": "首次参与", "value": str(metrics["first_start"] or "--"), "delta": first_delta},
            {"label": "最长连续", "value": _duration_short(int(metrics["longest_seconds"])), "delta": _delta_text(int(metrics["longest_seconds"]) - round(median(longest_baselines))) if baseline_allowed and longest_baselines else ""},
            {"label": "明显中断", "value": f"{metrics['interruptions']}次", "delta": _count_delta_text(int(metrics["interruptions"]) - round(median(interruption_baselines))) if baseline_allowed and interruption_baselines else ""},
        ],
    }


def _build_seven_day_rhythm(
    captured_now: datetime,
    daily_rows: list[dict],
    *,
    comparison_allowed: bool,
) -> dict[str, object]:
    end = captured_now.date() - timedelta(days=1)
    dates = [end - timedelta(days=offset) for offset in reversed(range(7))]
    prior = [dates[0] - timedelta(days=offset) for offset in reversed(range(1, 8))]
    row_map = _daily_row_map(daily_rows)
    history_start = (
        RHYTHM_HISTORY_START_DATE
        if captured_now.date() >= RHYTHM_HISTORY_START_DATE
        else date.min
    )
    display_points = [
        _rhythm_display_value(
            row_map.get(day.isoformat()),
            day,
            history_start=history_start,
        )
        for day in dates
    ]
    values = [point[0] for point in display_points]
    value_kinds = [point[1] for point in display_points]
    prior_values = [_trusted_work_seconds(row_map.get(day.isoformat())) for day in prior]
    display_dates = dates
    display_values = values
    display_kinds = value_kinds
    valid = [value for value in values if value is not None]
    trusted_valid = [
        int(value)
        for value, kind in zip(values, value_kinds)
        if value is not None and kind == "current"
    ]
    valid_prior = [value for value in prior_values if value is not None]
    comparable = comparison_allowed and len(trusted_valid) >= 3 and len(valid_prior) >= 3
    average = round(sum(valid) / len(valid)) if valid else 0
    prior_average = round(sum(valid_prior) / len(valid_prior)) if valid_prior else 0
    best_index = max(
        (index for index, value in enumerate(values) if value is not None),
        key=lambda index: int(values[index] or 0),
        default=None,
    )
    conclusion = (
        f"{dates[0].month}/{dates[0].day}–{dates[-1].month}/{dates[-1].day}"
        f" · 日均{_duration_short(average)}"
    )
    if comparable:
        conclusion += f"，{_delta_text(average - prior_average).replace('平时', '前7日')}"
    return {
        "title": "近7天工作节奏",
        "date_range": [dates[0].isoformat(), dates[-1].isoformat()],
        "status": {"label": "可比较" if comparable else "数据积累中", "kind": "baseline" if comparable else "waiting"},
        "conclusion": conclusion,
        "comparison": {"comparable": comparable, "delta_seconds": average - prior_average if comparable else None},
        "chart": {
            "kind": "bars",
            "labels": [f"{day.month}/{day.day}" for day in display_dates],
            "values": display_values,
            "value_kinds": display_kinds,
            "average_seconds": average if valid else None,
        },
        "metrics": [
            {"label": "日均参与", "value": _duration_short(average), "delta": ""},
            {
                "label": "最高一天",
                "value": (
                    f"{dates[best_index].month}/{dates[best_index].day} "
                    f"{_weekday_label(dates[best_index])}"
                    if best_index is not None
                    else "--"
                ),
                "delta": (
                    _duration_short(int(values[best_index] or 0))
                    if best_index is not None
                    else ""
                ),
            },
            {"label": "总时间", "value": _duration_short(sum(valid)), "delta": ""},
        ],
    }


def _build_thirty_day_rhythm(captured_now: datetime, daily_rows: list[dict]) -> dict[str, object]:
    end = captured_now.date() - timedelta(days=1)
    rolling_start = end - timedelta(days=29)
    start = (
        max(rolling_start, RHYTHM_HISTORY_START_DATE)
        if captured_now.date() >= RHYTHM_HISTORY_START_DATE
        else rolling_start
    )
    dates = [
        start + timedelta(days=offset)
        for offset in range(max(0, (end - start).days + 1))
    ]
    row_map = _daily_row_map(daily_rows)
    points = [
        _rhythm_display_value(
            row_map.get(day.isoformat()),
            day,
            history_start=start,
        )
        for day in dates
    ]
    values = [value for value, _kind in points]
    value_kinds = [kind for _value, kind in points]
    valid = [int(value) for value in values if value is not None]
    trusted_valid = [
        int(value)
        for value, kind in zip(values, value_kinds)
        if value is not None and kind == "current"
    ]
    average = round(sum(valid) / len(valid)) if valid else 0
    average_line = (
        round(sum(trusted_valid) / len(trusted_valid))
        if len(trusted_valid) >= 7
        else None
    )
    best_index = max(
        (index for index, value in enumerate(values) if value is not None),
        key=lambda index: int(values[index] or 0),
        default=None,
    )
    recent_dates = dates[-7:]
    prior_dates = dates[-14:-7]
    recent_values = [_trusted_work_seconds(row_map.get(day.isoformat())) for day in recent_dates]
    prior_values = [_trusted_work_seconds(row_map.get(day.isoformat())) for day in prior_dates]
    recent_valid = [value for value in recent_values if value is not None]
    prior_valid = [value for value in prior_values if value is not None]
    recent_delta: int | None = None
    if len(recent_valid) >= 3 and len(prior_valid) >= 3 and not _metric_break(daily_rows) and len(_classification_versions(daily_rows)) <= 1:
        recent_delta = round(sum(recent_valid) / len(recent_valid)) - round(sum(prior_valid) / len(prior_valid))
    return {
        "title": "近30天工作节奏",
        "date_range": [dates[0].isoformat(), dates[-1].isoformat()],
        "status": {"label": "可比较" if recent_delta is not None else "数据积累中", "kind": "baseline" if recent_delta is not None else "waiting"},
        "conclusion": (
            f"{dates[0].month}/{dates[0].day}–{dates[-1].month}/{dates[-1].day}"
            f" · 日均{_duration_short(average)}"
        ),
        "comparison": {"comparable": recent_delta is not None, "delta_seconds": recent_delta},
        "chart": {
            "kind": "bars",
            "labels": [f"{day.month}/{day.day}" for day in dates],
            "values": values,
            "value_kinds": value_kinds,
            "average_seconds": average_line,
        },
        "metrics": [
            {"label": "日均参与", "value": _duration_short(average), "delta": ""},
            {
                "label": "最高一天",
                "value": (
                    f"{dates[best_index].month}/{dates[best_index].day}"
                    if best_index is not None
                    else "--"
                ),
                "delta": (
                    _duration_short(int(values[best_index] or 0))
                    if best_index is not None
                    else ""
                ),
            },
            {"label": "总时间", "value": _duration_short(sum(valid)), "delta": ""},
        ],
    }


def build_rhythm_snapshot(
    *,
    captured_now: datetime,
    sessions: list[dict],
    daily_rows: list[dict],
    query_failed: bool,
) -> dict[str, object]:
    latest_session = max(
        sessions,
        key=lambda session: (
            str(session.get("date", "") or ""),
            str(session.get("end_time", "") or ""),
        ),
        default={},
    )
    current_metric_version = str(
        latest_session.get("metric_version", "attention-v1") or "attention-v1"
    )
    current_classification_version = str(
        latest_session.get("classification_version", "") or ""
    )
    has_session_metric_break = any(
        str(session.get("metric_version", "") or "") != current_metric_version
        for session in sessions
    )
    has_session_classification_break = bool(
        current_classification_version
        and any(
            str(session.get("classification_version", "") or "")
            != current_classification_version
            for session in sessions
        )
    )
    filtered_sessions = [
        session
        for session in sessions
        if str(session.get("metric_version", "") or "") == current_metric_version
        and (
            not current_classification_version
            or str(session.get("classification_version", "") or "")
            == current_classification_version
        )
    ]
    effective_daily_rows = list(daily_rows)
    classification_versions = _classification_versions(daily_rows)
    classification_break = (
        len(classification_versions) > 1
        or has_session_classification_break
    )
    if classification_break and captured_now.date() < RHYTHM_HISTORY_START_DATE:
        latest_row = max(
            (row for row in daily_rows if _day_has_metric_data(row)),
            key=lambda row: str(row.get("date", "") or ""),
            default={},
        )
        current_versions = {
            str(version or "")
            for version in (latest_row.get("classification_versions") or [])
            if str(version or "")
        }
        effective_daily_rows = [
            row
            for row in daily_rows
            if not _day_has_metric_data(row)
            or {
                str(version or "")
                for version in (row.get("classification_versions") or [])
                if str(version or "")
            } == current_versions
        ]
    comparison_allowed = (
        not query_failed
        and not _metric_break(daily_rows)
        and not has_session_metric_break
        and not classification_break
    )
    result = {
        "version": 1,
        "primary_metric": "work_engaged_seconds",
        "today": _build_today_rhythm(captured_now, filtered_sessions, daily_rows, query_failed=query_failed),
        "7d": _build_seven_day_rhythm(captured_now, effective_daily_rows, comparison_allowed=comparison_allowed),
        "30d": _build_thirty_day_rhythm(captured_now, effective_daily_rows),
    }
    unavailable_status: dict[str, str] | None = None
    if query_failed:
        unavailable_status = {"label": "暂不可比较", "kind": "unavailable"}
    elif _metric_break(daily_rows) or has_session_metric_break:
        unavailable_status = {"label": "口径已变化", "kind": "break"}
    elif classification_break:
        unavailable_status = {"label": "暂不可比较", "kind": "break"}
    if unavailable_status is not None:
        for mode in ("today", "7d", "30d"):
            result[mode]["status"] = dict(unavailable_status)
            result[mode]["comparison"] = {
                **dict(result[mode].get("comparison", {}) or {}),
                "comparable": False,
                "delta_seconds": None,
            }
        if (
            captured_now.date() >= RHYTHM_HISTORY_START_DATE
            and (
                _metric_break(daily_rows)
                or has_session_metric_break
                or classification_break
            )
        ):
            for mode in ("7d", "30d"):
                start_text, end_text = result[mode]["date_range"]
                start_day = datetime.strptime(start_text, "%Y-%m-%d").date()
                end_day = datetime.strptime(end_text, "%Y-%m-%d").date()
                result[mode]["conclusion"] = (
                    f"{start_day.month}/{start_day.day}–{end_day.month}/{end_day.day}"
                )
        elif classification_break:
            for mode in ("7d", "30d"):
                result[mode]["conclusion"] = "分类规则已变化，仅展示当前规则记录"
    return result


_SESSION_SECONDS_FIELDS = (
    "duration_seconds",
    "effective_seconds",
    "engaged_seconds",
    "passive_seconds",
    "idle_seconds",
)


def _sanitize_session(session: dict) -> dict | None:
    if session_row_is_anomalous(session):
        return None
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
        process_name = str(item.get("process_name") or "Unknown")
        display_name = resolve_display(process_name, app_details)
        seconds = parse_nonnegative_int(item.get("effective_seconds")) or 0
        identity = _stable_process_identity(process_name)
        bucket = merged.setdefault(
            identity,
            {
                "process_name": process_name.strip(),
                "display_name": display_name,
                "seconds": 0,
                "engaged_seconds": 0,
                "passive_seconds": 0,
                "purpose": "",
            },
        )
        bucket["seconds"] = int(bucket["seconds"]) + seconds
        bucket["engaged_seconds"] = int(bucket["engaged_seconds"]) + (
            parse_nonnegative_int(item.get("engaged_seconds")) or 0
        )
        bucket["passive_seconds"] = int(bucket["passive_seconds"]) + (
            parse_nonnegative_int(item.get("passive_seconds")) or 0
        )

    purposes: dict[str, dict[str, int]] = {}
    for detail in app_details:
        process_name = str(detail.get("process_name") or "Unknown")
        identity = _stable_process_identity(process_name)
        if identity not in merged:
            continue
        title = _safe_purpose_text(detail.get("window_title"))
        if not title:
            continue
        seconds = parse_nonnegative_int(detail.get("effective_seconds")) or 0
        purposes.setdefault(identity, {})[title] = (
            purposes.setdefault(identity, {}).get(title, 0) + seconds
        )
    for identity, titles in purposes.items():
        merged[identity]["purpose"] = max(
            titles.items(),
            key=lambda item: (item[1], item[0]),
        )[0]
    return sorted(merged.values(), key=lambda item: -int(item["seconds"]))[:9]


def _stable_process_identity(process_name: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(process_name or "Unknown")).strip()
    return _strip_executable_suffix(normalized).casefold()


def _safe_purpose_text(source: object) -> str:
    text = unicodedata.normalize("NFKC", str(source or "")).strip()
    if not text or any(unicodedata.category(char).startswith("C") for char in text):
        return ""
    return text


def build_work_episode_rows(
    sessions: list[dict],
    resolve_display,
) -> list[dict[str, object]]:
    """Group adjacent work-learning sessions into reviewable work episodes."""
    prepared: list[dict[str, object]] = []
    blockers: list[tuple[datetime, datetime]] = []
    for session in sessions:
        interval = _session_interval(session)
        if interval is None:
            continue
        if str(session.get("category_key", "") or "") not in WORK_KEYS:
            blockers.append(interval)
            continue
        engaged = parse_nonnegative_int(session.get("engaged_seconds"))
        metric_label = "参与"
        seconds = engaged
        if (
            (engaged is None or engaged == 0)
            and str(session.get("metric_version", "") or "") != "attention-v1"
        ):
            seconds = parse_nonnegative_int(session.get("effective_seconds"))
            metric_label = "有效"
        if seconds is None or seconds <= 0:
            continue
        process_name = str(session.get("process_name", "") or "Unknown")
        title = _safe_purpose_text(
            session.get("normalized_title") or session.get("window_title")
        )
        prepared.append(
            {
                "start": interval[0],
                "end": interval[1],
                "seconds": seconds,
                "metric_label": metric_label,
                "process_name": process_name,
                "display_name": str(resolve_display(process_name, []) or process_name),
                "title": title,
            }
        )
    prepared.sort(key=lambda item: (item["start"], item["end"]))

    groups: list[list[dict[str, object]]] = []
    for item in prepared:
        previous_end = (
            max(part["end"] for part in groups[-1]) if groups else None
        )
        interrupted = bool(
            previous_end is not None
            and any(
                block_start < item["start"] and block_end > previous_end
                for block_start, block_end in blockers
            )
        )
        if (
            not groups
            or interrupted
            or (item["start"] - previous_end).total_seconds()
            > RHYTHM_CONTINUITY_GAP_SECONDS
        ):
            groups.append([item])
        else:
            groups[-1].append(item)

    rows: list[dict[str, object]] = []
    for group in groups:
        app_seconds: dict[str, int] = {}
        title_seconds: dict[str, int] = {}
        for item in group:
            display_name = str(item["display_name"])
            app_seconds[display_name] = app_seconds.get(display_name, 0) + int(
                item["seconds"]
            )
            title = str(item["title"])
            generic_titles = {
                display_name.casefold(),
                _strip_executable_suffix(str(item["process_name"])).casefold(),
            }
            if title and title.casefold() not in generic_titles:
                title_seconds[title] = title_seconds.get(title, 0) + int(
                    item["seconds"]
                )
        apps = [
            name
            for name, _seconds in sorted(
                app_seconds.items(), key=lambda pair: (-pair[1], pair[0])
            )
        ]
        topic = (
            max(title_seconds.items(), key=lambda pair: (pair[1], pair[0]))[0]
            if title_seconds
            else " / ".join(apps)
        )
        rows.append(
            {
                "start_time": min(item["start"] for item in group).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "end_time": max(item["end"] for item in group).strftime(
                    "%Y-%m-%d %H:%M:%S"
                ),
                "topic": topic,
                "apps": apps,
                "seconds": sum(int(item["seconds"]) for item in group),
                "engaged_seconds": sum(
                    int(item["seconds"])
                    for item in group
                    if item["metric_label"] == "参与"
                ),
                "metric_label": (
                    "参与"
                    if all(item["metric_label"] == "参与" for item in group)
                    else "有效"
                ),
            }
        )
    return sorted(
        rows,
        key=lambda row: (-int(row["seconds"]), str(row["start_time"])),
    )


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


def load_today_snapshot(
    db_path: str,
    resolve_display,
    goal_settings: dict | None = None,
) -> dict[str, object]:
    captured_now = datetime.now()
    today_date = captured_now.date()
    today_str = today_date.strftime("%Y-%m-%d")
    yesterday_str = (captured_now - timedelta(days=1)).strftime("%Y-%m-%d")
    seven_day_dates = _rolling_date_strings(today_date, 7)
    fourteen_day_dates = _rolling_date_strings(today_date, 14)
    prior_seven_day_dates = fourteen_day_dates[:7]
    thirty_day_dates = _rolling_date_strings(today_date, 30)
    rhythm_session_dates = _rolling_date_strings(today_date, 31)

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
    rhythm_query_failed = False
    try:
        thirty_day_stats = database.query_date_range_stats(
            db_path,
            rhythm_session_dates,
        )
        rhythm_daily = list(thirty_day_stats.get("daily", []))
        thirty_day_date_set = set(thirty_day_dates)
        thirty_day_daily = [
            row
            for row in rhythm_daily
            if str(row.get("date", "") or "") in thirty_day_date_set
        ]
    except Exception:
        LOGGER.exception("Failed to read dashboard thirty-day range")
        thirty_day_stats = {"daily": []}
        thirty_day_daily = []
        rhythm_daily = []
        trusted_calculation_failed = True
        rhythm_query_failed = True
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
        raw_range_sessions = database.query_sessions_for_dates(
            db_path,
            rhythm_session_dates,
        )
        range_sessions, malformed_session_dates = _sanitize_sessions(
            raw_range_sessions
        )
        fourteen_day_set = set(fourteen_day_dates)
        fourteen_day_sessions = [
            session
            for session in range_sessions
            if str(session.get("date", "") or "") in fourteen_day_set
        ]
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
        rhythm_query_failed = True
        range_sessions = []
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

    try:
        rhythm = build_rhythm_snapshot(
            captured_now=captured_now,
            sessions=range_sessions,
            daily_rows=rhythm_daily,
            query_failed=rhythm_query_failed,
        )
    except Exception:
        LOGGER.exception("Failed to build dashboard rhythm model")
        rhythm = build_rhythm_snapshot(
            captured_now=captured_now,
            sessions=[],
            daily_rows=[],
            query_failed=True,
        )

    today_work_seconds = sum(
        parse_nonnegative_int(session.get("engaged_seconds")) or 0
        for session in sessions
        if str(session.get("category_key", "") or "") in WORK_KEYS
    )
    today_entertainment_seconds = category_seconds(stats)["entertainment"]
    goal_config = dict(goal_settings or {})
    try:
        goals = build_daily_goals(
            captured_now=captured_now,
            daily_rows=rhythm_daily,
            current_work_seconds=today_work_seconds,
            current_entertainment_seconds=today_entertainment_seconds,
            weekday_entertainment_limit_minutes=goal_config.get(
                "weekday_entertainment_limit_minutes", 60
            ),
            weekend_entertainment_limit_minutes=goal_config.get(
                "weekend_entertainment_limit_minutes", 120
            ),
            query_failed=(
                rhythm_query_failed or today_str in malformed_session_dates
            ),
        )
    except Exception:
        LOGGER.exception("Failed to build dashboard daily goals")
        goals = build_daily_goals(
            captured_now=captured_now,
            daily_rows=[],
            current_work_seconds=today_work_seconds,
            current_entertainment_seconds=today_entertainment_seconds,
            weekday_entertainment_limit_minutes=0,
            weekend_entertainment_limit_minutes=0,
            query_failed=True,
        )

    focus_summary, consecutive_days = build_focus_summary(db_path, today_str)
    try:
        recording_streak_days = database.count_recording_days(db_path)
    except Exception:
        LOGGER.exception("Failed to count consecutive recording days")
        recording_streak_days = 0
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
        "work_episode_rows": build_work_episode_rows(sessions, resolve_display),
        "focus_summary": focus_summary,
        "consecutive_days": consecutive_days,
        "recording_streak_days": recording_streak_days,
        "top_app_rows": build_top_app_rows(stats, resolve_display),
        "trust": trust,
        "comparison": comparison,
        "insight": insight,
        "rhythm": rhythm,
        "goals": goals,
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
