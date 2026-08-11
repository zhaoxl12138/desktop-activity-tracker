from __future__ import annotations

from daylens.services.trusted_metrics_service import assess_range, compare_ranges


def _summary(**overrides):
    summary = {
        "session_count": 200,
        "legacy_session_count": 0,
        "anomaly_count": 0,
        "dates_with_data": ["2026-07-01", "2026-07-02"],
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
    }
    summary.update(overrides)
    return summary


def test_complete_single_version_range_is_high_trust():
    result = assess_range(
        _summary(anomaly_count=1),
        ["2026-07-01", "2026-07-02"],
    )

    assert result == {
        "level": "high",
        "reasons": [],
        "coverage_ratio": 1.0,
        "legacy_ratio": 0.0,
        "anomaly_ratio": 0.005,
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
        "category_comparable": True,
    }


def test_multiple_classification_versions_are_medium_and_category_incomparable():
    result = assess_range(
        _summary(classification_versions=["rules-b", "rules-a", "rules-b"]),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["reasons"] == ["范围内存在多个分类版本"]
    assert result["classification_versions"] == ["rules-a", "rules-b"]
    assert result["category_comparable"] is False


def test_small_legacy_share_is_medium_with_stable_reason():
    result = assess_range(
        _summary(legacy_session_count=40),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["legacy_ratio"] == 0.2
    assert result["reasons"] == ["范围内包含少量旧计量口径"]


def test_mostly_legacy_range_is_low_trust():
    result = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=21,
            metric_versions=["legacy"],
            classification_versions=["legacy"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["旧计量口径占比超过20%"]


def test_multiple_metric_versions_alone_make_range_low_trust():
    result = assess_range(
        _summary(metric_versions=["attention-v2", "attention-v1"]),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["范围内存在多个计量版本"]


def test_anomaly_ratio_above_half_percent_is_low_trust():
    result = assess_range(
        _summary(session_count=199, anomaly_count=1),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["计时组成异常率超过0.5%"]


def test_low_trust_reasons_are_complete_and_deterministically_ordered():
    result = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=21,
            anomaly_count=1,
            dates_with_data=["2026-07-01"],
            metric_versions=["legacy", "attention-v1"],
            classification_versions=["rules-b", "rules-a"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == [
        "记录日期覆盖不足80%",
        "旧计量口径占比超过20%",
        "计时组成异常率超过0.5%",
        "范围内存在多个计量版本",
    ]
    assert result["category_comparable"] is False


def test_empty_range_never_reports_high_trust():
    result = assess_range(
        {
            "session_count": 0,
            "legacy_session_count": 0,
            "anomaly_count": 0,
            "dates_with_data": [],
            "metric_versions": [],
            "classification_versions": [],
        },
        [],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["范围内没有可评估记录"]
    assert result["coverage_ratio"] == 1.0
    assert result["legacy_ratio"] == 1.0
    assert result["anomaly_ratio"] == 0.0


def test_compare_ranges_allows_total_time_but_not_categories_after_rule_change():
    left = assess_range(
        _summary(classification_versions=["rules-a"]),
        ["2026-07-01", "2026-07-02"],
    )
    right = assess_range(
        _summary(classification_versions=["rules-b"]),
        ["2026-07-01", "2026-07-02"],
    )

    result = compare_ranges(left, right)

    assert result == {
        "comparable": True,
        "category_comparable": False,
        "reason": "分类规则不一致，仅总参与时间可比",
    }


def test_compare_ranges_rejects_low_quality_or_different_metric_versions():
    high = assess_range(
        _summary(),
        ["2026-07-01", "2026-07-02"],
    )
    low = assess_range(
        _summary(session_count=10, legacy_session_count=3),
        ["2026-07-01", "2026-07-02"],
    )
    different_metric = assess_range(
        _summary(metric_versions=["attention-v2"]),
        ["2026-07-01", "2026-07-02"],
    )

    assert compare_ranges(high, low) == {
        "comparable": False,
        "category_comparable": False,
        "reason": "数据质量不足，无法比较",
    }
    assert compare_ranges(high, different_metric) == {
        "comparable": False,
        "category_comparable": False,
        "reason": "计量版本不一致，无法比较",
    }
