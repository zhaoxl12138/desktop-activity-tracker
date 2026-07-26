"""Persistence helpers for rule editing and first-run classification."""

from __future__ import annotations

import yaml

from .. import database
from ..utils import normalize_rule_category_display_name, should_hide_rule_category


def load_rule_categories(config_path: str, db_path: str) -> dict[str, dict]:
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle) or {}

    categories = dict(config.get("categories", {}))
    custom = database.load_custom_rules(db_path)
    database.apply_custom_rules(config, custom)
    categories = config.get("categories", {})
    for key, rule in custom.items():
        if key not in categories:
            continue
        match = categories[key].setdefault("match", {})
        for mode_key in (
            "process_names_mode",
            "title_keywords_mode",
            "title_patterns_mode",
        ):
            match[mode_key] = rule.get(mode_key, "inherit")
    normalized: dict[str, dict] = {}
    for key, category in categories.items():
        display_name = normalize_rule_category_display_name(key, category.get("display_name", ""))
        if should_hide_rule_category(key, display_name):
            continue
        category["display_name"] = display_name
        normalized[key] = category
    return normalized


def save_rule_categories(db_path: str, categories: dict[str, dict]) -> None:
    payload: dict[str, dict] = {}
    for key, category in categories.items():
        match = category.get("match", {})
        payload[key] = {
            "display_name": category.get("display_name", ""),
            "active_rule": category.get("active_rule", "interactive_required"),
            "process_names": match.get("process_names", []),
            "process_names_mode": match.get("process_names_mode", "replace"),
            "title_keywords": match.get("title_keywords", []),
            "title_keywords_mode": match.get("title_keywords_mode", "replace"),
            "title_patterns": match.get("title_patterns", []),
            "title_patterns_mode": match.get("title_patterns_mode", "replace"),
        }
    database.save_custom_rules(db_path, payload)


def save_wizard_classifications(
    db_path: str,
    app_categories: dict[str, str | None],
    config: dict | None = None,
) -> None:
    factory_categories = (config or {}).get("categories", {})
    rules: dict[str, dict] = {}
    for process_name, category_key in app_categories.items():
        if category_key is None:
            continue
        factory = factory_categories.get(category_key, {})
        category = rules.setdefault(
            category_key,
            {
                "display_name": factory.get("display_name", category_key),
                "active_rule": factory.get(
                    "active_rule", "interactive_required"
                ),
                "process_names": [],
                "process_names_mode": "inherit",
                # Empty custom lists intentionally inherit current factory
                # title rules when categories are loaded.
                "title_keywords": [],
                "title_keywords_mode": "inherit",
                "title_patterns": [],
                "title_patterns_mode": "inherit",
            },
        )
        category["process_names"].append(process_name)

    database.merge_discovered_rules(
        db_path, rules, list(factory_categories)
    )
    database.save_settings(db_path, {"wizard_completed": "true"})


def save_scanned_rules(db_path: str, config: dict, classified: dict[str, list[str]]) -> int:
    factory_categories = config.get("categories", {})
    rules: dict[str, dict] = {}
    for category_key, process_names in classified.items():
        category = factory_categories.get(category_key, {})
        rules[category_key] = {
            "display_name": category.get("display_name", category_key),
            "active_rule": category.get("active_rule", "interactive_required"),
            "process_names": sorted(process_names),
            "process_names_mode": "inherit",
            "title_keywords": [],
            "title_keywords_mode": "inherit",
            "title_patterns": [],
            "title_patterns_mode": "inherit",
        }
    if not rules:
        return 0
    return database.merge_discovered_rules(
        db_path, rules, list(factory_categories)
    )
