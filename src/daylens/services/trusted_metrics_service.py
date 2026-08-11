"""Pure trust and comparability rules for aggregated attention metrics."""

from __future__ import annotations


def _sorted_versions(summary: dict, key: str) -> list[str]:
    return sorted(
        {
            str(version)
            for version in summary.get(key, []) or []
            if version is not None and str(version)
        }
    )


def assess_range(summary: dict, expected_dates: list[str]) -> dict[str, object]:
    """Assess the health of one aggregate without querying external state."""
    expected = set(expected_dates)
    recorded = set(summary.get("dates_with_data", []) or [])
    coverage_ratio = (
        len(recorded & expected) / len(expected) if expected else 1.0
    )
    session_count = int(summary.get("session_count", 0) or 0)
    legacy_count = int(summary.get("legacy_session_count", 0) or 0)
    anomaly_count = int(summary.get("anomaly_count", 0) or 0)
    metric_versions = _sorted_versions(summary, "metric_versions")
    classification_versions = _sorted_versions(
        summary,
        "classification_versions",
    )
    legacy_metric_present = "legacy" in metric_versions
    nonlegacy_metric_versions = [
        version for version in metric_versions if version != "legacy"
    ]
    if session_count > 0 and metric_versions == ["legacy"]:
        legacy_count = session_count
    legacy_ratio = legacy_count / session_count if session_count else 1.0
    anomaly_ratio = anomaly_count / session_count if session_count else 0.0

    low_reasons: list[str] = []
    if session_count <= 0:
        low_reasons.append("范围内没有可评估记录")
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
    both_healthy = left.get("level") != "low" and right.get("level") != "low"
    left_metrics = sorted(
        {
            str(version)
            for version in left.get("metric_versions", []) or []
            if version and str(version) != "legacy"
        }
    )
    right_metrics = sorted(
        {
            str(version)
            for version in right.get("metric_versions", []) or []
            if version and str(version) != "legacy"
        }
    )
    same_metric = bool(left_metrics) and left_metrics == right_metrics
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
