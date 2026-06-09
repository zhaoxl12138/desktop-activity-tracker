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
    for key, rule in custom.items():
        categories[key] = {
            "display_name": rule["display_name"],
            "active_rule": rule["active_rule"],
            "match": {
                "process_names": rule["process_names"],
                "title_keywords": rule["title_keywords"],
            },
        }
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
            "title_keywords": match.get("title_keywords", []),
        }
    database.save_custom_rules(db_path, payload)


def save_wizard_classifications(db_path: str, app_categories: dict[str, str | None]) -> None:
    rules: dict[str, dict] = {}
    for process_name, category_key in app_categories.items():
        if category_key is None:
            continue
        category = rules.setdefault(
            category_key,
            {
                "display_name": "",
                "active_rule": "",
                "process_names": [],
                "title_keywords": [],
            },
        )
        category["process_names"].append(process_name)

    database.save_custom_rules(db_path, rules)
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
            "title_keywords": [],
        }
    if not rules:
        return 0
    database.save_custom_rules(db_path, rules)
    return sum(len(rule["process_names"]) for rule in rules.values())
