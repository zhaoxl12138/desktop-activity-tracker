"""Classify foreground window into categories based on config.yaml rules."""

import hashlib
import json
import os
import re
import yaml

from . import get_app_root

# Categories that represent productive work — when they compete with
# video/entertainment, they win (content-is-king principle).
_LEARNING_CATEGORIES = {"reading", "coding", "ai_tools", "office", "creative"}

# Stable tie-breaking for categories with equally specific matches. This is
# the built-in rule order; title matches apply content-is-king separately.
_CATEGORY_PRIORITY = (
    "ai_tools",
    "coding",
    "office",
    "reading",
    "video",
    "creative",
    "gaming",
    "social",
    "tools",
    "browser_general",
    "other",
    "idle_leave",
)
_CATEGORY_PRIORITY_RANK = {
    key: index for index, key in enumerate(_CATEGORY_PRIORITY)
}
_ASCII_WORD_KEYWORD = re.compile(r"^[a-z0-9]+$")

_DEFAULT_BROWSER_PROCESSES = {
    "chrome.exe",
    "msedge.exe",
    "iexplore.exe",
    "firefox.exe",
    "msedgewebview2.exe",
    "chromium.exe",
    "brave.exe",
    "vivaldi.exe",
    "opera.exe",
    "360chrome.exe",
    "360chromex.exe",
    "qqbrowser.exe",
    "sogouexplorer.exe",
}


def _normalize_rule_values(values, *, case_insensitive):
    normalized = {str(value).strip() for value in (values or [])}
    if case_insensitive:
        normalized = {value.casefold() for value in normalized}
    return sorted(normalized)


def _canonical_rules(config):
    categories = config.get("categories", {}) or {}
    canonical = {}
    for key in sorted(categories):
        category = categories[key] or {}
        match = category.get("match", {}) or {}
        canonical[key] = {
            "active_rule": str(category.get("active_rule", "")),
            "process_names": _normalize_rule_values(
                match.get("process_names", []),
                case_insensitive=True,
            ),
            "title_keywords": _normalize_rule_values(
                match.get("title_keywords", []),
                case_insensitive=True,
            ),
            "title_patterns": _normalize_rule_values(
                match.get("title_patterns", []),
                case_insensitive=False,
            ),
        }
    return canonical


def _category_priority_key(key):
    return (_CATEGORY_PRIORITY_RANK.get(key, len(_CATEGORY_PRIORITY)), key)


def _keyword_matches(title_folded: str, keyword: str) -> bool:
    """Match ASCII word keywords without colliding inside larger words."""
    if not _ASCII_WORD_KEYWORD.fullmatch(keyword):
        return keyword in title_folded
    return re.search(
        rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])",
        title_folded,
    ) is not None


def _match_title(title_folded, match_rules, compiled_patterns=None):
    """Return (matched_keywords, matched_patterns) for title against rules."""
    kws = match_rules.get("title_keywords", [])
    matched_kws = [kw for kw in kws if _keyword_matches(title_folded, kw)]
    patterns = compiled_patterns or []
    matched_pats = [p.pattern for p in patterns if p.search(title_folded)]
    return matched_kws, matched_pats


class Classifier:
    @staticmethod
    def rule_fingerprint(config: dict) -> str:
        """Return a deterministic version for the effective classifier rules."""
        canonical = _canonical_rules(config)
        payload = json.dumps(
            canonical,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        return f"rules-{digest[:12]}"

    def __init__(self, config_path=None, db_path=None):
        if config_path is None:
            config_path = os.path.join(get_app_root(), "config", "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.categories = self.config.get("categories", {})

        # Merge custom rules from database (user overrides)
        if db_path and os.path.exists(db_path):
            from . import database
            database.merge_custom_rules(self.config, db_path)
            self.categories = self.config.get("categories", {})

        self.classification_version = self.rule_fingerprint(self.config)
        self._rules = _canonical_rules(self.config)
        self._category_items = sorted(
            self.categories.items(),
            key=lambda item: _category_priority_key(item[0]),
        )

        browser_match = self._rules.get("browser_general", {})
        self.browser_processes = _DEFAULT_BROWSER_PROCESSES | {
            process
            for process in browser_match.get("process_names", [])
            if process
        }
        self.idle_threshold = self.config.get("idle_threshold_seconds", 60)

        # Precompile regex patterns once at startup (avoid re.compile per tick)
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for key, _cat in self._category_items:
            patterns = self._rules[key]["title_patterns"]
            if patterns:
                self._compiled_patterns[key] = [re.compile(p) for p in patterns]

    def classify(self, process_name, window_title):
        """Return dict with category_key, category_name, active_rule, or fallback to 'other'."""
        if not process_name and not window_title:
            return self._fallback()

        process_name = (process_name or "").casefold()
        title_folded = (window_title or "").casefold()

        # First pass: match both process_names + title_keywords (highest specificity)
        title_matches = []
        for key, cat in self._category_items:
            if key in ("other", "browser_general"):
                continue
            match_rules = self._rules[key]
            proc_list = match_rules["process_names"]

            if proc_list and process_name in proc_list:
                compiled = self._compiled_patterns.get(key, [])
                matched_kws, matched_pats = _match_title(
                    title_folded,
                    match_rules,
                    compiled,
                )
                if matched_kws or matched_pats:
                    score = len(matched_kws) + len(matched_pats) * 2  # patterns weigh more
                    title_matches.append((key, cat, matched_kws, matched_pats, score))

        if title_matches:
            title_matches.sort(
                key=lambda match: (-match[4], _category_priority_key(match[0]))
            )
            best = self._apply_learning_priority(title_matches[0], title_matches)
            return {
                "category_key": best[0],
                "category_name": best[1]["display_name"],
                "active_rule": best[1]["active_rule"],
            }

        # Second pass: for browsers/WebView2, match by title_keywords/patterns only
        # msedgewebview2.exe is the Edge WebView2 runtime embedded by
        # desktop apps (Tencent Video, iQiyi, etc.). Treat it like a
        # browser so title-based classification works.
        if process_name in self.browser_processes:
            title_only_matches = []
            for key, cat in self._category_items:
                if key in ("other", "browser_general"):
                    continue
                compiled = self._compiled_patterns.get(key, [])
                matched_kws, matched_pats = _match_title(
                    title_folded,
                    self._rules[key],
                    compiled,
                )
                if matched_kws or matched_pats:
                    score = len(matched_kws) + len(matched_pats) * 2
                    title_only_matches.append((key, cat, matched_kws, matched_pats, score))
            if title_only_matches:
                title_only_matches.sort(
                    key=lambda match: (
                        -match[4],
                        _category_priority_key(match[0]),
                    )
                )
                best = self._apply_learning_priority(title_only_matches[0], title_only_matches)
                return {
                    "category_key": best[0],
                    "category_name": best[1]["display_name"],
                    "active_rule": best[1]["active_rule"],
                }

        # Third pass: match by process_names only
        proc_only_matches = []
        for key, cat in self._category_items:
            if key in ("other", "browser_general"):
                continue
            proc_list = self._rules[key]["process_names"]
            if proc_list and process_name in proc_list:
                proc_only_matches.append((key, cat))

        if proc_only_matches:
            best = proc_only_matches[0]
            # Content-is-king override: only for browsers. Desktop video
            # apps (iQiyi, Tencent Video) MUST NOT be reclassified by
            # title — their episode titles (第\d+集) collide with
            # learning patterns.
            if best[0] == "video" and process_name in self.browser_processes:
                for key, cat in self._category_items:
                    if key not in _LEARNING_CATEGORIES:
                        continue
                    compiled = self._compiled_patterns.get(key, [])
                    matched_kws, matched_pats = _match_title(
                        title_folded,
                        self._rules[key],
                        compiled,
                    )
                    if matched_kws or matched_pats:
                        best = (key, cat)
                        break
            return {
                "category_key": best[0],
                "category_name": best[1]["display_name"],
                "active_rule": best[1]["active_rule"],
            }

        # Browser general fallback
        bg = self.categories.get("browser_general", {})
        if process_name in self.browser_processes:
            return {
                "category_key": "browser_general",
                "category_name": bg.get("display_name", "浏览器"),
                "active_rule": bg.get("active_rule", "interactive_required"),
            }

        return self._fallback()

    def _apply_learning_priority(self, best, all_matches):
        """If best match is video but a learning category also matched, prefer learning.

        Content-is-king: watching a tutorial on Bilibili is learning, not entertainment.
        """
        if best[0] != "video":
            return best
        for m in all_matches:
            if m[0] in _LEARNING_CATEGORIES:
                return m
        return best

    def _fallback(self):
        other = self.categories.get("other", {})
        return {
            "category_key": "other",
            "category_name": other.get("display_name", "其他"),
            "active_rule": other.get("active_rule", "interactive_required"),
        }

    def is_effective(self, active_rule, idle_seconds):
        if active_rule == "passive_allowed":
            return True
        return idle_seconds <= self.idle_threshold
