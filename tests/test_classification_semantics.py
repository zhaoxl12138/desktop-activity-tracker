from daylens.services.classification_semantics import (
    CURRENT_CLASSIFICATION_POLICY,
    resolve_classification_semantics,
)


def test_manual_and_ai_versions_share_policy_but_keep_distinct_sources():
    manual = resolve_classification_semantics("manual-correction-v1")
    ai = resolve_classification_semantics("ai-high-backfill-v1")

    assert manual.policy_version == CURRENT_CLASSIFICATION_POLICY
    assert ai.policy_version == CURRENT_CLASSIFICATION_POLICY
    assert manual.source == "manual"
    assert ai.source == "ai"


def test_unknown_version_remains_a_conservative_policy_boundary():
    result = resolve_classification_semantics("foreign-policy-v9")

    assert result.policy_version == "unknown:foreign-policy-v9"
    assert result.source == "unknown"

