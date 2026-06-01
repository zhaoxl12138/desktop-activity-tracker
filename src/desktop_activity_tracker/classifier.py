"""Classify foreground window into categories based on config.yaml rules."""

import os
import yaml

from . import get_app_root


class Classifier:
    def __init__(self, config_path=None):
        if config_path is None:
            config_path = os.path.join(get_app_root(), "config", "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)
        self.categories = self.config.get("categories", {})
        self.idle_threshold = self.config.get("idle_threshold_seconds", 60)

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
            title_kws = [k.lower() for k in match_rules.get("title_keywords", [])]

            if proc_list and title_kws and process_name in proc_list:
                matched_kws = [kw for kw in title_kws if kw in title_lower]
                if matched_kws:
                    title_matches.append((key, cat, matched_kws))

        if title_matches:
            title_matches.sort(key=lambda x: (len(x[2]), max(len(kw) for kw in x[2])), reverse=True)
            best = title_matches[0]
            return {
                "category_key": best[0],
                "category_name": best[1]["display_name"],
                "active_rule": best[1]["active_rule"],
            }

        # Second pass: for browsers, match by title_keywords only (website-level classification)
        browser_procs = {"chrome.exe", "msedge.exe", "iexplore.exe", "firefox.exe"}
        if process_name in browser_procs:
            title_only_matches = []
            for key, cat in self.categories.items():
                if key in ("other", "browser_general"):
                    continue
                title_kws = [k.lower() for k in cat.get("match", {}).get("title_keywords", [])]
                matched_kws = [kw for kw in title_kws if kw in title_lower]
                if matched_kws:
                    title_only_matches.append((key, cat, matched_kws))
            if title_only_matches:
                title_only_matches.sort(key=lambda x: (len(x[2]), max(len(kw) for kw in x[2])), reverse=True)
                best = title_only_matches[0]
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
                "category_name": bg.get("display_name", "浏览器其他"),
                "active_rule": bg.get("active_rule", "interactive_required"),
            }

        return self._fallback()

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
