from __future__ import annotations

from copy import deepcopy

import pytest

from daylens.services.insights_service import select_primary_insight


def _payload(**overrides):
    payload = {
        "date_range": ["2026-07-28", "2026-08-10"],
        "trust": {
            "level": "high",
            "reasons": [],
            "category_comparable": True,
        },
    }
    payload.update(overrides)
    if isinstance(payload.get("best_window"), dict):
        payload["best_window"] = {
            "date_range": ["2026-07-28", "2026-08-10"],
            **payload["best_window"],
        }
    if isinstance(payload.get("interruptions"), dict):
        payload["interruptions"] = {
            "date_range": ["2026-08-04", "2026-08-10"],
            **payload["interruptions"],
        }
    if isinstance(payload.get("trend"), dict):
        payload["trend"] = {
            "prior_range": ["2026-07-28", "2026-08-03"],
            "recent_range": ["2026-08-04", "2026-08-10"],
            **payload["trend"],
        }
    if isinstance(payload.get("workflow"), dict):
        payload["workflow"] = {
            "date_range": ["2026-08-04", "2026-08-10"],
            **payload["workflow"],
        }
    return payload


def test_selects_a_qualified_best_window():
    insight = select_primary_insight(
        _payload(
            best_window={
                "workday_count": 6,
                "start_hour": 9,
                "end_hour": 11,
                "window_work_engaged_seconds": 3_200,
                "total_work_engaged_seconds": 10_000,
            }
        )
    )

    assert insight == {
        "kind": "best_window",
        "title": "你的优势时段是 09:00–11:00",
        "evidence": "最近14天有6个工作日，32%的工作参与时间集中在这里。",
        "action": "把最难的任务优先放进这个两小时窗口。",
        "confidence": "high",
        "date_range": ["2026-07-28", "2026-08-10"],
    }


def test_best_window_accepts_exact_sample_and_share_thresholds():
    insight = select_primary_insight(
        _payload(
            best_window={
                "workday_count": 5,
                "start_hour": 22,
                "end_hour": 24,
                "window_work_engaged_seconds": 3_000,
                "total_work_engaged_seconds": 10_000,
            }
        )
    )

    assert insight is not None
    assert insight["kind"] == "best_window"
    assert insight["title"] == "你的优势时段是 22:00–24:00"
    assert "30%" in insight["evidence"]


@pytest.mark.parametrize(
    "best_window",
    [
        {
            "workday_count": 4,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 3_000,
            "total_work_engaged_seconds": 10_000,
        },
        {
            "workday_count": 5,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 2_999,
            "total_work_engaged_seconds": 10_000,
        },
        {
            "workday_count": 5,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 0,
            "total_work_engaged_seconds": 0,
        },
    ],
)
def test_best_window_suppresses_insufficient_samples(best_window):
    assert select_primary_insight(_payload(best_window=best_window)) is None


def test_low_trust_always_returns_data_health_before_behavior_candidates():
    payload = _payload(
        trust={
            "level": "low",
            "reasons": ["范围内存在多个计量版本"],
            "category_comparable": False,
        },
        best_window={
            "workday_count": 10,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 5_000,
            "total_work_engaged_seconds": 10_000,
        },
        interruptions={
            "count": 20,
            "window_minutes": 15,
            "classification_comparable": True,
        },
    )

    assert select_primary_insight(payload) == {
        "kind": "data_health",
        "title": "先让数据口径稳定",
        "evidence": "范围内存在多个计量版本",
        "action": "继续记录，新旧口径不会被直接混合比较。",
        "confidence": "low",
        "date_range": ["2026-07-28", "2026-08-10"],
    }


def test_low_trust_uses_stable_default_reason_without_efficiency_judgment():
    insight = select_primary_insight(
        _payload(
            trust={
                "level": "low",
                "reasons": [],
                "category_comparable": False,
            }
        )
    )

    assert insight is not None
    assert insight["evidence"] == "新口径数据仍在积累"
    assert "效率" not in "".join(str(value) for value in insight.values())


@pytest.mark.parametrize(
    "untrusted_reason",
    [
        "分类规则发生变化",
        "你的效率下降了50%",
        "生产力需要提升",
        [],
        {},
    ],
)
def test_low_trust_never_echoes_unknown_or_behavioral_reasons(untrusted_reason):
    insight = select_primary_insight(
        _payload(
            trust={
                "level": "low",
                "reasons": [untrusted_reason],
                "category_comparable": False,
            }
        )
    )

    assert insight is not None
    assert insight["evidence"] == "新口径数据仍在积累"
    rendered = "".join(str(value) for value in insight.values())
    assert str(untrusted_reason) not in rendered
    assert "效率" not in rendered
    assert "生产力" not in rendered


def test_best_window_requires_a_matching_continuous_fourteen_day_period():
    common = {
        "workday_count": 6,
        "start_hour": 9,
        "end_hour": 11,
        "window_work_engaged_seconds": 3_200,
        "total_work_engaged_seconds": 10_000,
    }

    for section_range in (
        None,
        ["2026-08-10", "2026-08-10"],
        ["2026-07-27", "2026-08-09"],
    ):
        assert (
            select_primary_insight(
                _payload(
                    best_window={
                        **common,
                        "date_range": section_range,
                    }
                )
            )
            is None
        )


@pytest.mark.parametrize(
    "section_range",
    [
        None,
        ["2026-08-05", "2026-08-10"],  # six days
        ["2026-08-03", "2026-08-10"],  # eight days
        ["2026-07-28", "2026-08-03"],  # seven days, but not the latest seven
    ],
)
def test_interruptions_require_the_latest_continuous_seven_day_period(
    section_range,
):
    insight = select_primary_insight(
        _payload(
            interruptions={
                "date_range": section_range,
                "count": 8,
                "window_minutes": 15,
                "classification_comparable": True,
            }
        )
    )

    assert insight is None


@pytest.mark.parametrize(
    ("prior_range", "recent_range"),
    [
        (None, ["2026-08-04", "2026-08-10"]),
        (["2026-07-28", "2026-08-03"], None),
        # Both periods have seven days, but leave a one-day gap.
        (["2026-07-27", "2026-08-02"], ["2026-08-04", "2026-08-10"]),
        # Both periods have seven days, but overlap on 2026-08-04.
        (["2026-07-29", "2026-08-04"], ["2026-08-04", "2026-08-10"]),
    ],
)
def test_trend_requires_adjacent_non_overlapping_seven_day_periods(
    prior_range,
    recent_range,
):
    insight = select_primary_insight(
        _payload(
            trend={
                "prior_range": prior_range,
                "recent_range": recent_range,
                "recent_work_engaged_seconds": 15_000,
                "prior_work_engaged_seconds": 10_000,
                "comparison_comparable": True,
                "category_comparable": True,
            }
        )
    )

    assert insight is None


@pytest.mark.parametrize(
    "section_range",
    [None, ["2026-08-03", "2026-08-10"]],
)
def test_workflow_requires_the_latest_continuous_seven_day_period(section_range):
    insight = select_primary_insight(
        _payload(
            workflow={
                "date_range": section_range,
                "tool_count": 2,
                "switch_count": 8,
                "non_work_interruptions": 0,
                "tools": ["ChatGPT", "Codex"],
            }
        )
    )

    assert insight is None


def test_selects_qualified_external_interruptions():
    insight = select_primary_insight(
        _payload(
            interruptions={
                "count": 8,
                "window_minutes": 15,
                "classification_comparable": True,
            }
        )
    )

    assert insight == {
        "kind": "interruptions",
        "title": "外部打断开始影响工作连续性",
        "evidence": "最近7天，社交或娱乐在工作前后15分钟内出现了8次。",
        "action": "在优势时段静音，并集中安排一次消息处理窗口。",
        "confidence": "high",
        "date_range": ["2026-07-28", "2026-08-10"],
    }


@pytest.mark.parametrize(
    "interruptions",
    [
        {"count": 7, "window_minutes": 15, "classification_comparable": True},
        {"count": 8, "window_minutes": 14, "classification_comparable": True},
        {"count": 8, "window_minutes": 15, "classification_comparable": False},
    ],
)
def test_external_interruptions_require_the_exact_definition(interruptions):
    assert select_primary_insight(_payload(interruptions=interruptions)) is None


@pytest.mark.parametrize(
    ("recent", "prior", "direction", "action_fragment"),
    [
        (13_601, 10_000, "上升", "保留当前安排"),
        (10_000, 13_601, "下降", "回看最近一周"),
    ],
)
def test_selects_a_comparable_work_trend(
    recent,
    prior,
    direction,
    action_fragment,
):
    insight = select_primary_insight(
        _payload(
            trend={
                "recent_work_engaged_seconds": recent,
                "prior_work_engaged_seconds": prior,
                "comparison_comparable": True,
                "category_comparable": True,
            }
        )
    )

    assert insight is not None
    assert insight["kind"] == "trend"
    assert direction in insight["title"]
    assert action_fragment in insight["action"]
    assert "最近7天" in insight["evidence"]
    assert set(insight) == {
        "kind",
        "title",
        "evidence",
        "action",
        "confidence",
        "date_range",
    }


@pytest.mark.parametrize(
    ("recent", "prior"),
    [
        (24_000, 20_000),  # exactly 20%, even though the difference is > 1 hour
        (13_600, 10_000),  # exactly 1 hour, even though the percent is > 20%
        (0, 0),
    ],
)
def test_trend_requires_both_strict_change_thresholds(recent, prior):
    insight = select_primary_insight(
        _payload(
            trend={
                "recent_work_engaged_seconds": recent,
                "prior_work_engaged_seconds": prior,
                "comparison_comparable": True,
                "category_comparable": True,
            }
        )
    )

    assert insight is None


@pytest.mark.parametrize(
    ("comparison_comparable", "category_comparable"),
    [(False, True), (True, False)],
)
def test_work_trend_requires_total_and_category_comparability(
    comparison_comparable,
    category_comparable,
):
    insight = select_primary_insight(
        _payload(
            trend={
                "recent_work_engaged_seconds": 15_000,
                "prior_work_engaged_seconds": 10_000,
                "comparison_comparable": comparison_comparable,
                "category_comparable": category_comparable,
            }
        )
    )

    assert insight is None


def test_selects_a_collaborative_workflow_without_switching_warning():
    insight = select_primary_insight(
        _payload(
            workflow={
                "tool_count": 2,
                "switch_count": 8,
                "non_work_interruptions": 7,
                "tools": ["ChatGPT", "Codex"],
            }
        )
    )

    assert insight == {
        "kind": "workflow",
        "title": "你正在使用协作型工作流",
        "evidence": "ChatGPT、Codex 在同一工作域内切换了8次，非工作打断仅7次。",
        "action": "保留这套工具链，并为当前任务固定一个统一的笔记入口。",
        "confidence": "high",
        "date_range": ["2026-07-28", "2026-08-10"],
    }
    assert "过度切换" not in "".join(str(value) for value in insight.values())


@pytest.mark.parametrize(
    "workflow",
    [
        {
            "tool_count": 1,
            "switch_count": 8,
            "non_work_interruptions": 0,
            "tools": ["Codex"],
        },
        {
            "tool_count": 2,
            "switch_count": 7,
            "non_work_interruptions": 0,
            "tools": ["ChatGPT", "Codex"],
        },
        {
            "tool_count": 2,
            "switch_count": 8,
            "non_work_interruptions": 8,
            "tools": ["ChatGPT", "Codex"],
        },
    ],
)
def test_workflow_uses_stable_thresholds(workflow):
    assert select_primary_insight(_payload(workflow=workflow)) is None


def test_priority_is_best_window_then_interruptions_then_trend_then_workflow():
    behavior_candidates = {
        "best_window": {
            "workday_count": 5,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 3_000,
            "total_work_engaged_seconds": 10_000,
        },
        "interruptions": {
            "count": 8,
            "window_minutes": 15,
            "classification_comparable": True,
        },
        "trend": {
            "recent_work_engaged_seconds": 15_000,
            "prior_work_engaged_seconds": 10_000,
            "comparison_comparable": True,
            "category_comparable": True,
        },
        "workflow": {
            "tool_count": 2,
            "switch_count": 8,
            "non_work_interruptions": 0,
            "tools": ["ChatGPT", "Codex"],
        },
    }

    assert select_primary_insight(_payload(**behavior_candidates))["kind"] == (
        "best_window"
    )
    behavior_candidates.pop("best_window")
    assert select_primary_insight(_payload(**behavior_candidates))["kind"] == (
        "interruptions"
    )
    behavior_candidates.pop("interruptions")
    assert select_primary_insight(_payload(**behavior_candidates))["kind"] == (
        "trend"
    )
    behavior_candidates.pop("trend")
    assert select_primary_insight(_payload(**behavior_candidates))["kind"] == (
        "workflow"
    )


def test_medium_trust_can_emit_medium_confidence():
    payload = _payload(
        trust={
            "level": "medium",
            "reasons": ["记录日期未完全覆盖预期范围"],
            "category_comparable": True,
        },
        best_window={
            "workday_count": 5,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 3_000,
            "total_work_engaged_seconds": 10_000,
        },
    )

    assert select_primary_insight(payload)["confidence"] == "medium"


def test_mixed_classification_suppresses_every_behavior_candidate():
    payload = _payload(
        trust={
            "level": "medium",
            "reasons": ["分类规则发生变化"],
            "category_comparable": False,
        },
        best_window={
            "workday_count": 10,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": 5_000,
            "total_work_engaged_seconds": 10_000,
        },
        interruptions={
            "count": 20,
            "window_minutes": 15,
            "classification_comparable": True,
        },
        trend={
            "recent_work_engaged_seconds": 20_000,
            "prior_work_engaged_seconds": 10_000,
            "comparison_comparable": True,
            "category_comparable": True,
        },
        workflow={
            "tool_count": 2,
            "switch_count": 20,
            "non_work_interruptions": 0,
            "tools": ["ChatGPT", "Codex"],
        },
    )

    assert select_primary_insight(payload) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        "payload",
        {},
        {"date_range": ["2026-07-28", "2026-08-10"]},
        {"date_range": ["2026-08-10", "2026-07-28"], "trust": {"level": "low"}},
        {"date_range": ["not-a-date", "2026-08-10"], "trust": {"level": "low"}},
        {"date_range": "2026-07-28/2026-08-10", "trust": {"level": "low"}},
        {"date_range": ["2026-07-28", "2026-08-10"], "trust": {"level": "unknown"}},
    ],
)
def test_malformed_top_level_payload_fails_closed_without_raising(payload):
    assert select_primary_insight(payload) is None


@pytest.mark.parametrize(
    "bad_value",
    [True, False, -1, 1.5, float("nan"), float("inf"), "3000", None],
)
def test_malformed_best_window_numbers_fail_closed(bad_value):
    payload = _payload(
        best_window={
            "workday_count": 5,
            "start_hour": 9,
            "end_hour": 11,
            "window_work_engaged_seconds": bad_value,
            "total_work_engaged_seconds": 10_000,
        }
    )

    assert select_primary_insight(payload) is None


@pytest.mark.parametrize(
    ("section_name", "section"),
    [
        (
            "interruptions",
            {
                "count": True,
                "window_minutes": 15,
                "classification_comparable": True,
            },
        ),
        (
            "interruptions",
            {
                "count": 8,
                "window_minutes": float("inf"),
                "classification_comparable": True,
            },
        ),
        (
            "interruptions",
            {
                "count": 8,
                "window_minutes": 15,
                "classification_comparable": 1,
            },
        ),
        (
            "trend",
            {
                "recent_work_engaged_seconds": float("nan"),
                "prior_work_engaged_seconds": 10_000,
                "comparison_comparable": True,
                "category_comparable": True,
            },
        ),
        (
            "trend",
            {
                "recent_work_engaged_seconds": 15_000,
                "prior_work_engaged_seconds": -1,
                "comparison_comparable": True,
                "category_comparable": True,
            },
        ),
        (
            "workflow",
            {
                "tool_count": 2,
                "switch_count": 8.0,
                "non_work_interruptions": 0,
                "tools": ["ChatGPT", "Codex"],
            },
        ),
        (
            "workflow",
            {
                "tool_count": 2,
                "switch_count": 8,
                "non_work_interruptions": False,
                "tools": ["ChatGPT", "Codex"],
            },
        ),
    ],
)
def test_malformed_candidate_fields_fail_closed(section_name, section):
    assert select_primary_insight(_payload(**{section_name: section})) is None


@pytest.mark.parametrize(
    ("start_hour", "end_hour"),
    [(-1, 1), (0, 3), (9, 9), (23, 25), (True, 2), (9.0, 11)],
)
def test_invalid_best_window_hours_fail_closed(start_hour, end_hour):
    payload = _payload(
        best_window={
            "workday_count": 5,
            "start_hour": start_hour,
            "end_hour": end_hour,
            "window_work_engaged_seconds": 3_000,
            "total_work_engaged_seconds": 10_000,
        }
    )

    assert select_primary_insight(payload) is None


def test_workflow_rejects_inconsistent_or_malformed_tool_lists():
    common = {
        "tool_count": 2,
        "switch_count": 8,
        "non_work_interruptions": 0,
    }

    for tools in (
        ["ChatGPT"],
        ["ChatGPT", "ChatGPT"],
        ["ChatGPT", " Codex"],
        ["ChatGPT", 1],
        "ChatGPT,Codex",
    ):
        assert (
            select_primary_insight(
                _payload(workflow={**common, "tools": tools})
            )
            is None
        )


def test_selector_is_deterministic_and_does_not_mutate_input():
    payload = _payload(
        workflow={
            "tool_count": 3,
            "switch_count": 12,
            "non_work_interruptions": 2,
            "tools": ["ChatGPT", "Codex", "Obsidian"],
        }
    )
    before = deepcopy(payload)

    first = select_primary_insight(payload)
    second = select_primary_insight(payload)

    assert first == second
    assert payload == before
    assert isinstance(first, dict)
    assert set(first) == {
        "kind",
        "title",
        "evidence",
        "action",
        "confidence",
        "date_range",
    }
