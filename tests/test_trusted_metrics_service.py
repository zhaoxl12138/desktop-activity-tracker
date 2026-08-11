from __future__ import annotations

import pytest

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
    assess_range,
    compare_ranges,
)


def _summary(**overrides):
    summary = {
        "session_count": 200,
        "legacy_session_count": 0,
        "session_anomaly_count": 0,
        "legacy_log_sample_count": 0,
        "legacy_log_anomaly_count": 0,
        "legacy_granularity_unknown": False,
        "anomaly_count": 0,
        "dates_with_data": ["2026-07-01", "2026-07-02"],
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
    }
    summary.update(overrides)
    return summary


def test_data_health_reasons_are_exported_as_one_stable_contract():
    assert DATA_HEALTH_REASONS == frozenset(
        {
            REASON_FORMAT_INVALID,
            REASON_NO_RECORDS,
            REASON_LEGACY_GRANULARITY,
            REASON_LEGACY_LOG_ANOMALY,
            REASON_COVERAGE_BELOW_80,
            REASON_LEGACY_SHARE_ABOVE_20,
            REASON_TIMING_ANOMALY_ABOVE_LIMIT,
            REASON_MULTIPLE_METRIC_VERSIONS,
            REASON_MISSING_METRIC_VERSION,
        }
    )
    assert DATA_HEALTH_REASONS == frozenset(
        {
            "统计数据格式异常",
            "范围内没有可评估记录",
            "旧日志缺少会话粒度",
            "旧日志存在异常记录",
            "记录日期覆盖不足80%",
            "旧计量口径占比超过20%",
            "计时组成异常率超过0.5%",
            "范围内存在多个计量版本",
            "范围内缺少计量版本",
        }
    )


def test_complete_single_version_range_is_high_trust():
    result = assess_range(
        _summary(anomaly_count=1, session_anomaly_count=1),
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
        _summary(
            legacy_session_count=40,
            metric_versions=["attention-v1", "legacy"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["legacy_ratio"] == 0.2
    assert result["reasons"] == ["范围内包含少量旧计量口径"]


def test_one_percent_legacy_and_attention_v1_is_medium_not_low():
    result = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=1,
            metric_versions=["legacy", "attention-v1"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["legacy_ratio"] == 0.01
    assert result["reasons"] == ["范围内包含少量旧计量口径"]


def test_mostly_legacy_range_is_low_trust():
    result = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=21,
            metric_versions=["attention-v1", "legacy"],
            classification_versions=["legacy", "rules-a"],
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
        _summary(
            session_count=199,
            anomaly_count=1,
            session_anomaly_count=1,
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["计时组成异常率超过0.5%"]


def test_legacy_only_metric_cannot_be_high_when_count_is_inconsistent():
    result = assess_range(
        _summary(
            legacy_session_count=0,
            metric_versions=["legacy"],
            classification_versions=["legacy"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["legacy_ratio"] == 1.0
    assert result["reasons"] == ["统计数据格式异常"]
    assert result["category_comparable"] is False


def test_legacy_classification_cannot_receive_high_trust():
    result = assess_range(
        _summary(classification_versions=["legacy"]),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["reasons"] == ["分类口径仍为旧版本"]
    assert result["category_comparable"] is False


def test_low_trust_reasons_are_complete_and_deterministically_ordered():
    result = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=21,
            anomaly_count=1,
            session_anomaly_count=1,
            dates_with_data=["2026-07-01"],
            metric_versions=["legacy", "attention-v2", "attention-v1"],
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


@pytest.mark.parametrize(
    "field",
    [
        "session_count",
        "legacy_session_count",
        "session_anomaly_count",
        "legacy_log_sample_count",
        "legacy_log_anomaly_count",
        "anomaly_count",
    ],
)
@pytest.mark.parametrize(
    "bad_value",
    [None, True, -1, 1.0, float("nan"), float("inf"), "1", "oops"],
)
def test_malformed_counts_fail_closed_without_raising(field, bad_value):
    result = assess_range(
        _summary(**{field: bad_value}),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"][0] == "统计数据格式异常"


@pytest.mark.parametrize("bad_flag", [None, 0, 1, "false", "true"])
def test_granularity_flag_only_accepts_real_booleans(bad_flag):
    result = assess_range(
        _summary(legacy_granularity_unknown=bad_flag),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"][0] == "统计数据格式异常"


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("metric_versions", "attention-v1"),
        ("metric_versions", ["attention-v1", 1]),
        ("classification_versions", "rules-a"),
        ("classification_versions", [None]),
        ("dates_with_data", "2026-07-01"),
        ("dates_with_data", ["2026-07-01", None]),
    ],
)
def test_malformed_version_or_date_collections_fail_closed(field, bad_value):
    result = assess_range(
        _summary(**{field: bad_value}),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"][0] == "统计数据格式异常"


def test_expected_dates_must_match_summary_scope_to_receive_trust():
    empty_expected = assess_range(_summary(), [])
    extra_recorded_date = assess_range(
        _summary(dates_with_data=["2026-07-03"]),
        ["2026-07-01", "2026-07-02"],
    )
    malformed_expected = assess_range(_summary(), "2026-07-01")

    for result in (empty_expected, extra_recorded_date, malformed_expected):
        assert result["level"] == "low"
        assert result["reasons"][0] == "统计数据格式异常"


def test_partial_expected_date_coverage_cannot_receive_high_trust():
    result = assess_range(
        _summary(
            dates_with_data=[
                "2026-07-01",
                "2026-07-02",
                "2026-07-03",
                "2026-07-04",
            ]
        ),
        [
            "2026-07-01",
            "2026-07-02",
            "2026-07-03",
            "2026-07-04",
            "2026-07-05",
        ],
    )

    assert result["coverage_ratio"] == 0.8
    assert result["level"] == "medium"
    assert result["reasons"] == ["记录日期未完全覆盖预期范围"]


def test_well_formed_legacy_log_granularity_flag_is_not_a_format_error():
    result = assess_range(
        _summary(
            legacy_log_sample_count=1,
            legacy_granularity_unknown=True,
            metric_versions=["attention-v1", "legacy"],
            classification_versions=["legacy", "rules-a"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["旧日志缺少会话粒度"]


@pytest.mark.parametrize(
    ("summary", "expected_dates"),
    [
        (
            _summary(
                session_count=1,
                dates_with_data=["2026-07-01", "2026-07-02"],
            ),
            ["2026-07-01", "2026-07-02"],
        ),
        (
            _summary(
                session_count=1,
                dates_with_data=["2026-07-01"],
                metric_versions=["attention-v1", "legacy"],
            ),
            ["2026-07-01"],
        ),
        (
            _summary(
                legacy_log_sample_count=1,
                legacy_granularity_unknown=True,
                metric_versions=["attention-v1"],
                classification_versions=["legacy", "rules-a"],
            ),
            ["2026-07-01", "2026-07-02"],
        ),
        (
            _summary(
                legacy_log_sample_count=1,
                legacy_granularity_unknown=True,
                metric_versions=["attention-v1", "legacy"],
                classification_versions=["rules-a"],
            ),
            ["2026-07-01", "2026-07-02"],
        ),
        (
            _summary(
                session_count=1,
                dates_with_data=["2026-07-01"],
                metric_versions=["attention-v1", "attention-v2"],
            ),
            ["2026-07-01"],
        ),
        (
            _summary(
                session_count=1,
                dates_with_data=["2026-07-01"],
                classification_versions=["rules-a", "rules-b"],
            ),
            ["2026-07-01"],
        ),
    ],
)
def test_cross_field_source_contradictions_are_format_errors(
    summary,
    expected_dates,
):
    result = assess_range(summary, expected_dates)
    valid = assess_range(
        _summary(),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "low"
    assert result["reasons"] == ["统计数据格式异常"]
    assert result["category_comparable"] is False
    assert compare_ranges(result, valid) == {
        "comparable": False,
        "category_comparable": False,
        "reason": "数据质量不足，无法比较",
    }


def test_multiple_classification_versions_are_valid_with_enough_sessions():
    result = assess_range(
        _summary(
            session_count=2,
            classification_versions=["rules-b", "rules-a"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert result["level"] == "medium"
    assert result["reasons"] == ["范围内存在多个分类版本"]


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


def test_compare_ranges_keeps_legacy_as_a_metric_compatibility_boundary():
    mixed = assess_range(
        _summary(
            session_count=100,
            legacy_session_count=1,
            metric_versions=["legacy", "attention-v1"],
            classification_versions=["legacy", "rules-a"],
        ),
        ["2026-07-01", "2026-07-02"],
    )
    current = assess_range(
        _summary(
            metric_versions=["attention-v1"],
            classification_versions=["rules-a"],
        ),
        ["2026-07-01", "2026-07-02"],
    )

    assert compare_ranges(mixed, current) == {
        "comparable": False,
        "category_comparable": False,
        "reason": "计量版本不一致，无法比较",
    }


def test_compare_ranges_fails_closed_when_trust_level_is_missing_or_unknown():
    complete = {
        "level": "high",
        "metric_versions": ["attention-v1"],
        "classification_versions": ["rules-a"],
        "category_comparable": True,
    }

    for level in (None, "unknown"):
        incomplete = {**complete, "level": level}
        assert compare_ranges(incomplete, complete) == {
            "comparable": False,
            "category_comparable": False,
            "reason": "数据质量不足，无法比较",
        }
