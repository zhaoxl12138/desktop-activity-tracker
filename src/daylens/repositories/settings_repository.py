"""Persistence helpers for user settings and custom rules."""

from __future__ import annotations

import os
import sqlite3

SETTING_KEYS = [
    "sample_interval_seconds",
    "idle_threshold_seconds",
    "flush_interval_seconds",
    "min_session_seconds",
    "obsidian_output_path",
    "theme",
    "startup_enabled",
    "wizard_completed",
]


def load_settings(db_path: str) -> dict[str, str] | None:
    if not os.path.exists(db_path):
        return None
    conn = sqlite3.connect(db_path)
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    if not rows:
        return None
    return {key: value for key, value in rows if key}


def save_settings(db_path: str, settings_dict: dict) -> None:
    conn = sqlite3.connect(db_path)
    for key in SETTING_KEYS:
        if key in settings_dict:
            value = settings_dict[key]
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (key, str(value) if value is not None else ""),
            )
    conn.commit()
    conn.close()


def merge_db_settings(config: dict, db_path: str) -> None:
    db_settings = load_settings(db_path)
    if db_settings is None:
        seed = {key: config.get(key, "") for key in SETTING_KEYS}
        tracker = config.get("tracker", {})
        for key in (
            "sample_interval_seconds",
            "idle_threshold_seconds",
            "flush_interval_seconds",
            "min_session_seconds",
        ):
            if key in tracker:
                seed[key] = tracker[key]
        save_settings(db_path, seed)
        return

    for key in SETTING_KEYS:
        if key not in db_settings or not db_settings[key]:
            continue
        value = db_settings[key]
        if key in (
            "sample_interval_seconds",
            "idle_threshold_seconds",
            "flush_interval_seconds",
            "min_session_seconds",
        ):
            try:
                config[key] = int(value)
            except ValueError:
                continue
            config.setdefault("tracker", {})[key] = config[key]
        elif key == "startup_enabled":
            config[key] = value.lower() in ("true", "1", "yes")
        else:
            config[key] = value


def load_custom_rules(db_path: str) -> dict[str, dict]:
    if not os.path.exists(db_path):
        return {}
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM custom_rules").fetchall()
    conn.close()
    result: dict[str, dict] = {}
    for row in rows:
        result[row["category_key"]] = {
            "display_name": row["display_name"],
            "active_rule": row["active_rule"],
            "process_names": [item for item in (row["process_names"] or "").split("\n") if item],
            "title_keywords": [item for item in (row["title_keywords"] or "").split("\n") if item],
        }
    return result


def save_custom_rules(db_path: str, rules_dict: dict[str, dict]) -> None:
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM custom_rules")
    for key, rule in rules_dict.items():
        conn.execute(
            "INSERT INTO custom_rules (category_key, display_name, active_rule, process_names, title_keywords) VALUES (?, ?, ?, ?, ?)",
            (
                key,
                rule.get("display_name", ""),
                rule.get("active_rule", "interactive_required"),
                "\n".join(rule.get("process_names", [])),
                "\n".join(rule.get("title_keywords", [])),
            ),
        )
    conn.commit()
    conn.close()


def merge_custom_rules(config: dict, db_path: str) -> None:
    custom_rules = load_custom_rules(db_path)
    if not custom_rules:
        return

    categories = config.setdefault("categories", {})
    for key, rule in custom_rules.items():
        base_category = categories.get(key, {})
        base_match = base_category.get("match", {}) if isinstance(base_category, dict) else {}
        title_keywords = rule["title_keywords"] or list(
            base_match.get("title_keywords", []) or []
        )
        categories[key] = {
            "display_name": rule["display_name"],
            "active_rule": rule["active_rule"],
            "match": {
                "process_names": rule["process_names"],
                "title_keywords": title_keywords,
            },
        }


def delete_activity_logs_before(db_path: str, cutoff_date: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM activity_logs WHERE date < ?", (cutoff_date,))
        conn.commit()
    finally:
        conn.close()
