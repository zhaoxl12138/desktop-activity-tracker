"""Classify foreground window into categories based on config.yaml rules."""

import os
import re
import yaml

from . import get_app_root

# Categories that represent productive work — when they compete with
# video/entertainment, they win (content-is-king principle).
_LEARNING_CATEGORIES = {"reading", "coding", "ai_tools", "office", "creative"}


def _match_title(title_lower, match_rules, compiled_patterns=None):
    """Return (matched_keywords, matched_patterns) for title against rules."""
    kws = [k.lower() for k in match_rules.get("title_keywords", [])]
    matched_kws = [kw for kw in kws if kw in title_lower]
    patterns = compiled_patterns or []
    matched_pats = [p.pattern for p in patterns if p.search(title_lower)]
    return matched_kws, matched_pats


class Classifier:
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

        self.idle_threshold = self.config.get("idle_threshold_seconds", 60)

        # Precompile regex patterns once at startup (avoid re.compile per tick)
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for key, cat in self.categories.items():
            patterns = cat.get("match", {}).get("title_patterns", []) or []
            if patterns:
                self._compiled_patterns[key] = [re.compile(p) for p in patterns]

    def classify(self, process_name, window_title):
        """Return dict with category_key, category_name, active_rule, or fallback to 'other'."""
        if not process_name and not window_title:
            return self._fallback()

        process_name = (process_name or "").lower()
        window_title = (window_title or "").lower()
        title_lower = window_title

        # First pass: match both process_names + title_keywords (highest specificity)
        title_matches = []
        for key, cat in self.categories.items():
            if key == "other":
                continue
            match_rules = cat.get("match", {})
            proc_list = [p.lower() for p in match_rules.get("process_names", [])]

            if proc_list and process_name in proc_list:
                compiled = self._compiled_patterns.get(key, [])
                matched_kws, matched_pats = _match_title(title_lower, match_rules, compiled)
                if matched_kws or matched_pats:
                    score = len(matched_kws) + len(matched_pats) * 2  # patterns weigh more
                    title_matches.append((key, cat, matched_kws, matched_pats, score))

        if title_matches:
            title_matches.sort(key=lambda x: x[4], reverse=True)
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
        browser_procs = {"chrome.exe", "msedge.exe", "iexplore.exe", "firefox.exe",
                         "msedgewebview2.exe"}
        if process_name in browser_procs:
            title_only_matches = []
            for key, cat in self.categories.items():
                if key in ("other", "browser_general"):
                    continue
                compiled = self._compiled_patterns.get(key, [])
                matched_kws, matched_pats = _match_title(title_lower, cat.get("match", {}), compiled)
                if matched_kws or matched_pats:
                    score = len(matched_kws) + len(matched_pats) * 2
                    title_only_matches.append((key, cat, matched_kws, matched_pats, score))
            if title_only_matches:
                title_only_matches.sort(key=lambda x: x[4], reverse=True)
                best = self._apply_learning_priority(title_only_matches[0], title_only_matches)
                return {
                    "category_key": best[0],
                    "category_name": best[1]["display_name"],
                    "active_rule": best[1]["active_rule"],
                }

        # Third pass: match by process_names only
        proc_only_matches = []
        for key, cat in self.categories.items():
            if key in ("other", "browser_general"):
                continue
            proc_list = [p.lower() for p in cat.get("match", {}).get("process_names", [])]
            if proc_list and process_name in proc_list:
                proc_only_matches.append((key, cat))

        if proc_only_matches:
            best = proc_only_matches[0]
            # Content-is-king override: only for browsers. Desktop video
            # apps (iQiyi, Tencent Video) MUST NOT be reclassified by
            # title — their episode titles (第\d+集) collide with
            # learning patterns.
            if best[0] == "video" and process_name in browser_procs:
                for key, cat in self.categories.items():
                    if key not in _LEARNING_CATEGORIES:
                        continue
                    compiled = self._compiled_patterns.get(key, [])
                    matched_kws, matched_pats = _match_title(title_lower, cat.get("match", {}), compiled)
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
        bg_procs = [p.lower() for p in bg.get("match", {}).get("process_names", [])]
        if bg_procs and process_name in bg_procs:
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
