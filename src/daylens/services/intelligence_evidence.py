"""Durable, privacy-safe evidence used by AI title classification."""

from __future__ import annotations

import hashlib
import json
import re
from functools import wraps
from datetime import datetime
from pathlib import Path

from .intelligence_client import LEGAL_CATEGORIES
from .intelligence_state import atomic_json
from .classification_state_service import state_operation, state_transaction, read_state, write_state


_BROWSER_SUFFIX = re.compile(
    r"\s*[-—|]\s*(?:Google Chrome|Microsoft Edge|Mozilla Firefox|"
    r"360(?:安全|极速)?浏览器\w*|Chrome|Edge)\s*$",
    re.I,
)


def redact_title(title: str) -> str:
    """Return the bounded title representation allowed in durable AI state."""
    value = str(title or "").strip()
    value = re.sub(r"https?://\S+|www\.\S+", "[网址]", value, flags=re.I)
    value = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[邮箱]", value)
    value = re.sub(r"(?<!\d)\d{7,}(?!\d)", "[号码]", value)
    value = re.sub(r"[A-Za-z]:[\\/][^\s]+", "[路径]", value)
    value = re.sub(r"(?i)\b(?:sk-|Bearer\s+)[A-Za-z0-9_-]+", "[密钥]", value)
    value = re.sub(r"\s+", " ", value).strip()
    return _BROWSER_SUFFIX.sub("", value)[:180]


def _pattern_tokens(title: str) -> frozenset[str]:
    value = redact_title(title).casefold()
    value = re.sub(r"\b20\d{2}[-/.年]\d{1,2}(?:[-/.月]\d{1,2}日?)?\b", " ", value)
    value = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", value)
    value = re.sub(r"\d+", " ", value)
    segments = re.findall(r"[a-z][a-z0-9_+-]{2,}|[\u3400-\u9fff]{2,}", value)
    tokens: set[str] = set()
    for segment in segments:
        if segment in {'网址', '邮箱', '号码', '路径', '密钥'}:
            continue
        if re.fullmatch(r"[\u3400-\u9fff]+", segment):
            if len(segment) <= 3:
                tokens.add(segment)
            else:
                tokens.update(segment[index:index + 3] for index in range(len(segment) - 2))
        else:
            tokens.add(segment)
    return frozenset(tokens)


def _pattern_id(process: str, tokens: frozenset[str]) -> str:
    raw = f"{str(process).strip().casefold()}|{'|'.join(sorted(tokens))}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def load_patterns(directory) -> list[dict]:
    try:
        data = read_state(directory, 'title_patterns.json', {})
        rows = data.get("patterns") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            return []
        from .intelligence_state import _valid_custom
        return [row for row in rows if isinstance(row, dict) and
                (row.get("category") in LEGAL_CATEGORIES or _valid_custom(row))]
    except (OSError, ValueError, TypeError):
        return []


def save_patterns(directory, patterns: list[dict]) -> None:
    write_state(directory, 'title_patterns.json', {"version": 1, "patterns": patterns})


@state_operation
def save_pattern(directory, process, title, category, *, categories=None) -> dict:
    from ..category_registry import category_definition
    definition = category_definition(category, categories)
    if definition is None or not definition.manual_allowed or category in {"browser_general", "other"}:
        raise ValueError("不支持的分类")
    app = str(process or "").strip().casefold()
    example = redact_title(title)
    tokens = _pattern_tokens(example)
    if not app or len(tokens) < 2:
        raise ValueError("标题信息不足，无法形成相似模式")
    now = datetime.now().isoformat(timespec="seconds")
    identity = _pattern_id(app, tokens)
    patterns = load_patterns(directory)
    row = {
        "id": identity,
        "app": app[:80],
        "category": category,
        "example": example,
        "tokens": sorted(tokens),
        "enabled": True,
        "created_at": now,
        "last_used_at": now,
        "hit_count": 0,
    }
    if category not in LEGAL_CATEGORIES:
        row.update(custom_category=True, timing_policy_id=definition.timing_policy)
    patterns = [item for item in patterns if item.get("id") != identity]
    patterns.append(row)
    save_patterns(directory, patterns[-100:])
    return row


@state_operation
def set_pattern_enabled(directory, pattern_id: str, enabled: bool, *, include_exact=True) -> bool:
    patterns = load_patterns(directory)
    changed = False
    for row in patterns:
        if row.get("id") == pattern_id:
            row["enabled"] = bool(enabled)
            changed = True
    if changed:
        save_patterns(directory, patterns)
        if include_exact:
            _update_linked_decisions(directory, pattern_id, enabled=bool(enabled))
    return changed


def _update_linked_decisions(directory, pattern_id, **fields):
    from .intelligence_state import load_overrides
    overrides = load_overrides(directory)
    changed = False
    for decision in overrides.values():
        if decision.get('pattern_id') == pattern_id:
            decision.update(fields)
            changed = True
    if changed:
        write_state(directory, 'manual_decisions.json', overrides)


@state_operation
def update_pattern_category(directory, pattern_id: str, category: str, *, categories=None) -> bool:
    """Keep pattern identity and matching exact manual decisions consistent."""
    from ..category_registry import category_definition
    definition = category_definition(category,categories)
    if definition is None or not definition.manual_allowed:
        raise ValueError('不支持的分类')
    patterns = load_patterns(directory)
    row = next((item for item in patterns if item.get('id') == pattern_id), None)
    if row is None:
        return False
    if row.get('category') == category:
        return True
    from .intelligence_state import load_overrides, title_context, DEFAULT_SETTINGS
    overrides = load_overrides(directory)
    for identity, decision in overrides.items():
        if decision.get('pattern_id') == pattern_id:
            decision['category'] = category
            if category not in LEGAL_CATEGORIES:
                decision.update(custom_category=True, timing_policy_id=definition.timing_policy)
    # Write exact decisions first: these take precedence in the classifier.
    if overrides:
        write_state(directory, 'manual_decisions.json', overrides)
    row['category'] = category
    if category not in LEGAL_CATEGORIES:
        row.update(custom_category=True, timing_policy_id=definition.timing_policy)
    save_patterns(directory, patterns)
    return True


@state_operation
def delete_pattern(directory, pattern_id: str) -> bool:
    patterns = load_patterns(directory)
    kept = [row for row in patterns if row.get("id") != pattern_id]
    if len(kept) == len(patterns):
        return False
    save_patterns(directory, kept)
    _update_linked_decisions(directory, pattern_id, enabled=False)
    return True


def match_pattern(patterns: list[dict], process, title, *, threshold: float = 0.72) -> dict | None:
    app = str(process or "").strip().casefold()
    candidate = _pattern_tokens(title)
    if len(candidate) < 2:
        return None
    best: tuple[float, dict] | None = None
    for row in patterns:
        if not row.get("enabled", True) or row.get("app") != app:
            continue
        stored = frozenset(str(value) for value in row.get("tokens", []) if value)
        overlap = candidate & stored
        if len(overlap) < 2:
            continue
        score = len(overlap) / len(candidate | stored)
        coverage = len(overlap) / min(len(candidate), len(stored))
        strong_shared_phrase = len(overlap) >= 4 and coverage >= 0.55
        if (score >= threshold or strong_shared_phrase) and (best is None or score > best[0]):
            best = (score, row)
    if best is None:
        return None
    score, row = best
    return {
        "status": "applied",
        "source": "人工模式",
        "category": row["category"],
        "suggested_category": row["category"],
        "certainty": "high",
        "reason": "命中用户确认的相似标题模式",
        "evidence": ["manual_pattern"],
        "pattern_id": row["id"],
        "apply": True,
        "similarity": round(score, 3),
    }


def _queue_operation(function):
    @wraps(function)
    def wrapped(self, *args, **kwargs):
        with state_transaction(self.path.parent):
            self._items = self._load()
            if function.__name__ == 'resolve':
                from .classification_decisions import decision_command
                return decision_command(lambda directory: function(self,*args,**kwargs))(self.path.parent)
            return function(self, *args, **kwargs)
    return wrapped


class ReviewQueue:
    """Bounded local queue of uncertain AI classifications."""

    def __init__(self, directory, *, limit: int = 100):
        self.path = Path(directory) / "classification_reviews.json"
        self.limit = max(1, int(limit))
        self._items = self._load()

    def _load(self) -> dict[str, dict]:
        try:
            data = read_state(self.path.parent, self.path.name, {})
            self._resolved = dict(data.get('resolved', {})) if isinstance(data, dict) else {}
            rows = data.get("items") if isinstance(data, dict) else None
            if not isinstance(rows, list):
                return {}
            return {row["id"]: row for row in rows if isinstance(row, dict) and isinstance(row.get("id"), str)}
        except (OSError, ValueError, TypeError):
            self._resolved = {}
            return {}

    def _save(self) -> None:
        resolved = dict(sorted(self._resolved.items(), key=lambda item:str(item[1]))[-1000:])
        write_state(self.path.parent, self.path.name, {"version": 1, "items": self.items(), 'resolved':resolved})

    def items(self) -> list[dict]:
        return sorted(self._items.values(), key=lambda row: str(row.get("last_seen", "")), reverse=True)

    @_queue_operation
    def upsert(self, context: dict) -> None:
        identity = str(context.get("id") or "")
        if not identity or identity in self._resolved:
            return
        now = datetime.now().isoformat(timespec="microseconds")
        old = self._items.get(identity, {})
        self._items[identity] = {
            "id": identity,
            "manual_id": str(context.get('manual_id') or old.get('manual_id') or '')[:24],
            "app": str(context.get("app") or "")[:80],
            "title": redact_title(context.get("title") or ""),
            "suggested_category": str(context.get("category") or ""),
            "certainty": str(context.get("certainty") or ""),
            "reason": str(context.get("reason") or "")[:80],
            "evidence": list(context.get("evidence") or [])[:8],
            "occurrences": int(old.get("occurrences") or 0) + 1,
            "active_seconds": int(old.get("active_seconds") or 0) + max(0, int(context.get("active_seconds") or 0)),
            "first_seen": old.get("first_seen") or now,
            "last_seen": now,
        }
        ordered = self.items()[:self.limit]
        self._items = {row["id"]: row for row in ordered}
        self._save()

    @_queue_operation
    def ignore(self, identity: str) -> bool:
        removed = self._items.pop(str(identity), None) is not None
        self._resolved[str(identity)] = datetime.now().isoformat(timespec='microseconds')
        if removed:
            self._save()
        return removed

    @_queue_operation
    def resolve(self, identity: str, category: str, *, scope='similar', categories=None) -> dict:
        row = self._items.get(str(identity))
        if row is None:
            raise KeyError(identity)
        from .intelligence_state import save_override, load_overrides, title_context, DEFAULT_SETTINGS
        # Confirmation always saves an exact decision. Similarity is optional.
        save_override(self.path.parent, row['app'], row['title'], category, scope=scope, categories=categories)
        if row.get('manual_id'):
            overrides = load_overrides(self.path.parent)
            context = title_context(row['app'], row['title'], dict(DEFAULT_SETTINGS), 'manual-v1')
            decision = dict(overrides[context['id']])
            overrides[row['manual_id']] = decision
            # The redacted representation must not become a shared exact key.
            if context['id'] != row['manual_id']:
                overrides.pop(context['id'], None)
            write_state(self.path.parent, 'manual_decisions.json', overrides)
        pattern = next((item for item in load_patterns(self.path.parent)
                        if item.get('app') == row['app'] and item.get('example') == row['title']),
                       {'category': category, 'source': '手动'})
        self.ignore(identity)
        return pattern
