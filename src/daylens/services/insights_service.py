"""Select one deterministic, local insight from pre-aggregated metrics."""

from __future__ import annotations

import unicodedata
from datetime import date

from daylens.services.trusted_metrics_service import (
    DATA_HEALTH_REASONS,
    REASON_COVERAGE_BELOW_80,
    REASON_FORMAT_INVALID,
    REASON_LEGACY_GRANULARITY,
    REASON_LEGACY_LOG_ANOMALY,
    REASON_LEGACY_SHARE_ABOVE_20,
    REASON_MISSING_METRIC_VERSION,
    REASON_MULTIPLE_METRIC_VERSIONS,
    REASON_NO_RECORDS,
    REASON_TIMING_ANOMALY_ABOVE_LIMIT,
)


_DEFAULT_HEALTH_REASON = "新口径数据仍在积累"
_DEFAULT_HEALTH_ACTION = "继续记录，新旧口径不会被直接混合比较。"
_CONTINUE_WITHOUT_MIXING_ACTION = (
    "继续记录，并避免直接混合比较新旧或不同版本数据。"
)
_CHECK_RECORDING_ACTION = "检查记录状态和数据文件，确认异常后再查看趋势。"
_DATA_HEALTH_ACTIONS = {
    REASON_FORMAT_INVALID: _CHECK_RECORDING_ACTION,
    REASON_NO_RECORDS: "继续记录，积累同一口径数据后再查看趋势。",
    REASON_LEGACY_GRANULARITY: (
        "旧日志缺少可比粒度，请避免与新口径直接比较。"
    ),
    REASON_LEGACY_LOG_ANOMALY: _CHECK_RECORDING_ACTION,
    REASON_COVERAGE_BELOW_80: _CONTINUE_WITHOUT_MIXING_ACTION,
    REASON_LEGACY_SHARE_ABOVE_20: _CONTINUE_WITHOUT_MIXING_ACTION,
    REASON_TIMING_ANOMALY_ABOVE_LIMIT: _CHECK_RECORDING_ACTION,
    REASON_MULTIPLE_METRIC_VERSIONS: _CONTINUE_WITHOUT_MIXING_ACTION,
    REASON_MISSING_METRIC_VERSION: _CHECK_RECORDING_ACTION,
}
_INSIGHT_FIELDS = frozenset(("kind", "title", "evidence", "action"))
_MAX_TOOL_NAME_LENGTH = 64


def _nonnegative_int(value) -> int | None:
    if type(value) is not int or value < 0:
        return None
    return value


def _real_bool(value) -> bool | None:
    return value if type(value) is bool else None


def _parse_date_range(value) -> list[str] | None:
    if type(value) is not list or len(value) != 2:
        return None
    parsed: list[date] = []
    for item in value:
        if type(item) is not str or not item or item.strip() != item:
            return None
        try:
            parsed_date = date.fromisoformat(item)
        except ValueError:
            return None
        if parsed_date.isoformat() != item:
            return None
        parsed.append(parsed_date)
    if parsed[0] > parsed[1]:
        return None
    return list(value)


def _parse_period_range(value, inclusive_days: int) -> list[str] | None:
    parsed_range = _parse_date_range(value)
    if parsed_range is None:
        return None
    start = date.fromisoformat(parsed_range[0])
    end = date.fromisoformat(parsed_range[1])
    if (end - start).days != inclusive_days - 1:
        return None
    return parsed_range


def _matching_period(
    payload: dict,
    section: dict,
    inclusive_days: int,
    *,
    require_full_range: bool,
) -> list[str] | None:
    main_range = _parse_date_range(payload.get("date_range"))
    period = _parse_period_range(section.get("date_range"), inclusive_days)
    if main_range is None or period is None:
        return None
    if require_full_range:
        return period if period == main_range else None
    if period[1] != main_range[1] or period[0] < main_range[0]:
        return None
    return period


def _rounded_percent(numerator: int, denominator: int) -> int:
    return (numerator * 100 + denominator // 2) // denominator


def _format_duration(seconds: int) -> str:
    hours, remainder = divmod(seconds, 3_600)
    minutes = remainder // 60
    if hours and minutes:
        return f"{hours}小时{minutes}分钟"
    if hours:
        return f"{hours}小时"
    return f"{minutes}分钟"


def _unsafe_tool_character(character: str) -> bool:
    category = unicodedata.category(character)
    return character in "<>&" or category.startswith("C") or category in {
        "Zl",
        "Zp",
    }


def build_best_window_candidate(payload: dict) -> dict | None:
    """Build the two-hour concentration-window candidate."""
    section = payload.get("best_window")
    if not isinstance(section, dict):
        return None
    if (
        _matching_period(
            payload,
            section,
            14,
            require_full_range=True,
        )
        is None
    ):
        return None

    workdays = _nonnegative_int(section.get("workday_count"))
    start_hour = _nonnegative_int(section.get("start_hour"))
    end_hour = _nonnegative_int(section.get("end_hour"))
    window_seconds = _nonnegative_int(
        section.get("window_work_engaged_seconds")
    )
    total_seconds = _nonnegative_int(section.get("total_work_engaged_seconds"))
    values = (workdays, start_hour, end_hour, window_seconds, total_seconds)
    if any(value is None for value in values):
        return None
    if workdays < 5 or workdays > 14:
        return None
    if start_hour > 22 or end_hour > 24 or end_hour - start_hour != 2:
        return None
    if total_seconds <= 0 or window_seconds > total_seconds:
        return None
    if window_seconds * 10 < total_seconds * 3:
        return None

    percentage = _rounded_percent(window_seconds, total_seconds)
    return {
        "kind": "best_window",
        "title": f"你的优势时段是 {start_hour:02d}:00–{end_hour:02d}:00",
        "evidence": (
            f"最近14天有{workdays}个工作日，"
            f"{percentage}%的工作参与时间集中在这里。"
        ),
        "action": "把最难的任务优先放进这个两小时窗口。",
    }


def build_interruption_candidate(payload: dict) -> dict | None:
    """Build a candidate for social/entertainment interruptions around work."""
    section = payload.get("interruptions")
    if not isinstance(section, dict):
        return None
    if (
        _matching_period(
            payload,
            section,
            7,
            require_full_range=False,
        )
        is None
    ):
        return None

    count = _nonnegative_int(section.get("count"))
    window_minutes = _nonnegative_int(section.get("window_minutes"))
    comparable = _real_bool(section.get("classification_comparable"))
    if count is None or window_minutes is None or comparable is not True:
        return None
    if count < 8 or window_minutes != 15:
        return None
    return {
        "kind": "interruptions",
        "title": "工作前后频繁出现社交或娱乐",
        "evidence": (
            "最近7天，社交或娱乐在工作前后"
            f"{window_minutes}分钟内出现了{count}次。"
        ),
        "action": "在需要连续工作的时段静音或集中处理社交与娱乐通知。",
    }


def build_trend_candidate(payload: dict) -> dict | None:
    """Build a candidate for a safely comparable work-engagement trend."""
    section = payload.get("trend")
    if not isinstance(section, dict):
        return None

    main_range = _parse_date_range(payload.get("date_range"))
    prior_range = _parse_period_range(section.get("prior_range"), 7)
    recent_range = _parse_period_range(section.get("recent_range"), 7)
    if main_range is None or prior_range is None or recent_range is None:
        return None
    prior_end = date.fromisoformat(prior_range[1])
    recent_start = date.fromisoformat(recent_range[0])
    if (recent_start - prior_end).days != 1:
        return None
    if main_range != [prior_range[0], recent_range[1]]:
        return None

    recent = _nonnegative_int(section.get("recent_work_engaged_seconds"))
    prior = _nonnegative_int(section.get("prior_work_engaged_seconds"))
    comparison_comparable = _real_bool(
        section.get("comparison_comparable")
    )
    category_comparable = _real_bool(section.get("category_comparable"))
    if recent is None or prior is None or prior <= 0:
        return None
    if comparison_comparable is not True or category_comparable is not True:
        return None

    difference = recent - prior
    absolute_difference = abs(difference)
    if absolute_difference <= 3_600:
        return None
    if absolute_difference * 5 <= prior:
        return None

    direction = "上升" if difference > 0 else "下降"
    difference_word = "多" if difference > 0 else "少"
    percentage = _rounded_percent(absolute_difference, prior)
    action = (
        "保留当前安排，继续观察一周是否稳定。"
        if difference > 0
        else "回看最近一周的会议、打断和任务安排，找出变化原因。"
    )
    return {
        "kind": "trend",
        "title": f"最近7天工作参与时间{direction}了 {percentage}%",
        "evidence": (
            f"最近7天比此前7天{difference_word}了"
            f"{_format_duration(absolute_difference)}的工作参与时间。"
        ),
        "action": action,
    }


def build_workflow_candidate(payload: dict) -> dict | None:
    """Build a positive candidate for repeated switches within one work domain."""
    section = payload.get("workflow")
    if not isinstance(section, dict):
        return None
    if (
        _matching_period(
            payload,
            section,
            7,
            require_full_range=False,
        )
        is None
    ):
        return None

    tool_count = _nonnegative_int(section.get("tool_count"))
    switch_count = _nonnegative_int(section.get("switch_count"))
    interruptions = _nonnegative_int(section.get("non_work_interruptions"))
    tools = section.get("tools")
    if tool_count is None or switch_count is None or interruptions is None:
        return None
    if type(tools) is not list or len(tools) != tool_count:
        return None

    normalized_tools: list[str] = []
    unique_tools: set[str] = set()
    for tool in tools:
        if type(tool) is not str or not tool or tool.strip() != tool:
            return None
        display_name = unicodedata.normalize("NFKC", tool)
        if (
            not display_name
            or display_name.strip() != display_name
            or len(display_name) > _MAX_TOOL_NAME_LENGTH
            or any(_unsafe_tool_character(char) for char in display_name)
        ):
            return None
        uniqueness_key = display_name.casefold()
        if uniqueness_key in unique_tools:
            return None
        unique_tools.add(uniqueness_key)
        normalized_tools.append(display_name)
    if tool_count < 2 or switch_count < 8 or interruptions >= 8:
        return None

    return {
        "kind": "workflow",
        "title": "你正在使用协作型工作流",
        "evidence": (
            f"{'、'.join(normalized_tools)} 在同一工作域内切换了"
            f"{switch_count}次，非工作打断仅{interruptions}次。"
        ),
        "action": "保留这套工具链，并为当前任务固定一个统一的笔记入口。",
    }


def _data_health_candidate(trust: dict) -> dict:
    reasons = trust.get("reasons", [])
    reason = _DEFAULT_HEALTH_REASON
    action = _DEFAULT_HEALTH_ACTION
    if isinstance(reasons, (list, tuple)) and reasons:
        first_reason = reasons[0]
        if (
            type(first_reason) is str
            and first_reason in DATA_HEALTH_REASONS
        ):
            reason = first_reason
            action = _DATA_HEALTH_ACTIONS.get(
                first_reason,
                _CHECK_RECORDING_ACTION,
            )
    return {
        "kind": "data_health",
        "title": "先让数据口径稳定",
        "evidence": reason,
        "action": action,
    }


def select_primary_insight(payload: dict) -> dict | None:
    """Return the highest-priority eligible insight, if one exists.

    ``payload`` contains an ISO ``date_range`` pair, a trust assessment, and
    optional pre-aggregated ``best_window``, ``interruptions``, ``trend``, and
    ``workflow`` sections.  The best-window section covers the full 14-day
    range; interruption and workflow sections cover its latest seven days;
    trend supplies adjacent ``prior_range`` and ``recent_range`` seven-day
    pairs spanning the full range.  This function never queries or mutates
    external state; malformed or incomplete candidate sections are simply
    ineligible.
    """
    if not isinstance(payload, dict):
        return None
    date_range = _parse_date_range(payload.get("date_range"))
    trust = payload.get("trust")
    if date_range is None or not isinstance(trust, dict):
        return None

    level = trust.get("level")
    if type(level) is not str or level not in {"high", "medium", "low"}:
        return None
    if level == "low":
        candidate = _data_health_candidate(trust)
    else:
        if _real_bool(trust.get("category_comparable")) is not True:
            return None
        candidate = None
        for builder in (
            build_best_window_candidate,
            build_interruption_candidate,
            build_trend_candidate,
            build_workflow_candidate,
        ):
            candidate = builder(payload)
            if candidate is not None:
                break
    if candidate is None or set(candidate) != _INSIGHT_FIELDS:
        return None
    return {
        **candidate,
        "confidence": level,
        "date_range": date_range,
    }
