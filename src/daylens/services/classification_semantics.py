"""Separate classification policy compatibility from decision provenance."""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..classifier import CLASSIFICATION_POLICY_VERSION


CURRENT_CLASSIFICATION_POLICY = CLASSIFICATION_POLICY_VERSION
_RULE_FINGERPRINT = re.compile(r"^rules-[a-z0-9]+$")


@dataclass(frozen=True)
class ClassificationSemantics:
    policy_version: str
    source: str
    decision_version: str


def resolve_classification_semantics(version: object) -> ClassificationSemantics:
    """Resolve old overloaded version values without rewriting history."""
    decision = str(version or "").strip()
    if decision == "legacy":
        return ClassificationSemantics("legacy", "legacy", decision)
    if decision.startswith("manual-"):
        return ClassificationSemantics(CURRENT_CLASSIFICATION_POLICY, "manual", decision)
    if decision.startswith("ai-"):
        return ClassificationSemantics(CURRENT_CLASSIFICATION_POLICY, "ai", decision)
    if _RULE_FINGERPRINT.fullmatch(decision):
        return ClassificationSemantics(CURRENT_CLASSIFICATION_POLICY, "local_rule", decision)
    return ClassificationSemantics(f"unknown:{decision or 'missing'}", "unknown", decision)


def policy_versions(versions: list[str]) -> list[str]:
    return sorted({resolve_classification_semantics(value).policy_version for value in versions})
