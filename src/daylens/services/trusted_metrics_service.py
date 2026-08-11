"""Pure trust and comparability rules for aggregated attention metrics."""

from __future__ import annotations

from datetime import date


_STRING_COLLECTION_TYPES = (list, tuple, set, frozenset)


def _nonnegative_integer(value) -> tuple[int, bool]:
    if type(value) is not int or value < 0:
        return 0, False
    return value, True


def _string_collection(value) -> tuple[list[str], bool]:
    if not isinstance(value, _STRING_COLLECTION_TYPES):
        return [], False
    normalized: set[str] = set()
    for item in value:
        if type(item) is not str or not item or item.strip() != item:
            return [], False
        normalized.add(item)
    return sorted(normalized), True


def _date_collection(value) -> tuple[list[str], bool]:
    values, valid = _string_collection(value)
    if not valid:
        return [], False
    for value_str in values:
        try:
            parsed = date.fromisoformat(value_str)
        except ValueError:
            return [], False
        if parsed.isoformat() != value_str:
            return [], False
    return values, True


def assess_range(summary: dict, expected_dates: list[str]) -> dict[str, object]:
    """Assess the health of one aggregate without querying external state."""
    payload = summary if isinstance(summary, dict) else {}
    format_valid = isinstance(summary, dict)

    count_keys = (
        "session_count",
        "legacy_session_count",
        "session_anomaly_count",
        "legacy_log_sample_count",
        "legacy_log_anomaly_count",
        "anomaly_count",
    )
    counts: dict[str, int] = {}
    for key in count_keys:
        raw_value = payload.get(key, 0)
        counts[key], valid = _nonnegative_integer(raw_value)
        format_valid = format_valid and valid

    raw_flag = payload.get("legacy_granularity_unknown", False)
    flag_valid = type(raw_flag) is bool
    legacy_granularity_unknown = raw_flag if flag_valid else False
    format_valid = format_valid and flag_valid

    metric_versions, metric_versions_valid = _string_collection(
        payload.get("metric_versions", [])
    )
    classification_versions, classification_versions_valid = (
        _string_collection(payload.get("classification_versions", []))
    )
    recorded_dates, recorded_dates_valid = _date_collection(
        payload.get("dates_with_data", [])
    )
    expected_dates_list, expected_dates_valid = _date_collection(expected_dates)
    format_valid = (
        format_valid
        and metric_versions_valid
        and classification_versions_valid
        and recorded_dates_valid
        and expected_dates_valid
    )

    session_count = counts["session_count"]
    legacy_count = counts["legacy_session_count"]
    session_anomaly_count = counts["session_anomaly_count"]
    legacy_log_sample_count = counts["legacy_log_sample_count"]
    legacy_log_anomaly_count = counts["legacy_log_anomaly_count"]
    anomaly_count = counts["anomaly_count"]

    if legacy_count > session_count:
        format_valid = False
    if session_anomaly_count > session_count:
        format_valid = False
    if legacy_log_anomaly_count > legacy_log_sample_count:
        format_valid = False
    if anomaly_count != session_anomaly_count + legacy_log_anomaly_count:
        format_valid = False
    if legacy_granularity_unknown != (legacy_log_sample_count > 0):
        format_valid = False

    expected = set(expected_dates_list)
    recorded = set(recorded_dates)
    has_data = session_count > 0 or legacy_log_sample_count > 0
    if not expected and (has_data or recorded):
        format_valid = False
    if expected and recorded - expected:
        format_valid = False
    if has_data != bool(recorded):
        format_valid = False
    coverage_ratio = (
        len(recorded & expected) / len(expected)
        if expected
        else (1.0 if not has_data and not recorded else 0.0)
    )

    legacy_metric_present = "legacy" in metric_versions
    nonlegacy_metric_versions = [
        version for version in metric_versions if version != "legacy"
    ]
    if session_count > 0 and metric_versions == ["legacy"]:
        if legacy_count != session_count:
            format_valid = False
        legacy_count = session_count
    if legacy_count > 0 and not legacy_metric_present:
        format_valid = False
    legacy_ratio = legacy_count / session_count if session_count else 1.0
    anomaly_ratio = (
        session_anomaly_count / session_count if session_count else 0.0
    )

    if not format_valid:
        return {
            "level": "low",
            "reasons": ["统计数据格式异常"],
            "coverage_ratio": coverage_ratio,
            "legacy_ratio": legacy_ratio,
            "anomaly_ratio": anomaly_ratio,
            "metric_versions": metric_versions,
            "classification_versions": classification_versions,
            "category_comparable": False,
        }

    low_reasons: list[str] = []
    if session_count <= 0 and not legacy_granularity_unknown:
        low_reasons.append("范围内没有可评估记录")
    if legacy_granularity_unknown:
        low_reasons.append("旧日志缺少会话粒度")
    if legacy_log_anomaly_count > 0:
        low_reasons.append("旧日志存在异常记录")
    if coverage_ratio < 0.8:
        low_reasons.append("记录日期覆盖不足80%")
    if session_count > 0 and legacy_ratio > 0.2:
        low_reasons.append("旧计量口径占比超过20%")
    if anomaly_ratio > 0.005:
        low_reasons.append("计时组成异常率超过0.5%")
    if len(nonlegacy_metric_versions) > 1:
        low_reasons.append("范围内存在多个计量版本")
    elif session_count > 0 and not metric_versions:
        low_reasons.append("范围内缺少计量版本")

    if low_reasons:
        level = "low"
        reasons = low_reasons
    else:
        medium_reasons: list[str] = []
        if coverage_ratio < 1.0:
            medium_reasons.append("记录日期未完全覆盖预期范围")
        if legacy_ratio > 0 or legacy_metric_present:
            medium_reasons.append("范围内包含少量旧计量口径")
        if len(classification_versions) > 1:
            medium_reasons.append("范围内存在多个分类版本")
        elif not classification_versions:
            medium_reasons.append("范围内缺少分类版本")
        elif classification_versions == ["legacy"]:
            medium_reasons.append("分类口径仍为旧版本")
        level = "medium" if medium_reasons else "high"
        reasons = medium_reasons

    return {
        "level": level,
        "reasons": reasons,
        "coverage_ratio": coverage_ratio,
        "legacy_ratio": legacy_ratio,
        "anomaly_ratio": anomaly_ratio,
        "metric_versions": metric_versions,
        "classification_versions": classification_versions,
        "category_comparable": (
            level != "low"
            and len(classification_versions) == 1
            and classification_versions != ["legacy"]
        ),
    }


def compare_ranges(left: dict, right: dict) -> dict[str, object]:
    """Report whether total and category trends can be compared safely."""
    trusted_levels = {"high", "medium"}
    both_healthy = (
        left.get("level") in trusted_levels
        and right.get("level") in trusted_levels
    )
    left_metrics, left_metrics_valid = _string_collection(
        left.get("metric_versions", [])
    )
    right_metrics, right_metrics_valid = _string_collection(
        right.get("metric_versions", [])
    )
    same_metric = (
        left_metrics_valid
        and right_metrics_valid
        and bool(left_metrics)
        and left_metrics == right_metrics
    )
    comparable = both_healthy and same_metric
    category_comparable = (
        comparable
        and bool(left.get("category_comparable"))
        and bool(right.get("category_comparable"))
        and left.get("classification_versions")
        == right.get("classification_versions")
    )

    if not both_healthy:
        reason = "数据质量不足，无法比较"
    elif not same_metric:
        reason = "计量版本不一致，无法比较"
    elif not category_comparable:
        reason = "分类规则不一致，仅总参与时间可比"
    else:
        reason = ""
    return {
        "comparable": comparable,
        "category_comparable": category_comparable,
        "reason": reason,
    }
