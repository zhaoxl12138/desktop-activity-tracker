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
            "title_patterns": [item for item in (row["title_patterns"] or "").split("\n") if item],
        }
    return result


def save_custom_rules(db_path: str, rules_dict: dict[str, dict]) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM custom_rules")
        for key, rule in rules_dict.items():
            _upsert_custom_rule(conn, key, rule)
        conn.commit()
    finally:
        conn.close()


def merge_discovered_rules(
    db_path: str,
    incoming_rules: dict[str, dict],
    category_priority: list[str] | None = None,
) -> int:
    """Incrementally merge discovered processes without replacing user rules.

    Existing process ownership wins over discovery. Conflicting new discoveries
    use the factory category order, then category key, for a stable owner.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT * FROM custom_rules").fetchall()
        rules = {
            row["category_key"]: {
                "display_name": row["display_name"] or "",
                "active_rule": row["active_rule"] or "interactive_required",
                "process_names": _split_rule_list(row["process_names"]),
                "title_keywords": _split_rule_list(row["title_keywords"]),
                "title_patterns": _split_rule_list(row["title_patterns"]),
            }
            for row in rows
        }
        priority = {
            key: index for index, key in enumerate(category_priority or [])
        }

        def category_order(key: str) -> tuple[int, str]:
            return (priority.get(key, len(priority)), key.casefold())

        owner: dict[str, str] = {}
        for category_key in sorted(rules, key=category_order):
            unique: list[str] = []
            for process_name in rules[category_key]["process_names"]:
                folded = process_name.casefold()
                if folded in owner:
                    continue
                owner[folded] = category_key
                unique.append(process_name)
            rules[category_key]["process_names"] = unique

        candidates: dict[str, list[tuple[str, str]]] = {}
        for category_key, rule in incoming_rules.items():
            for process_name in rule.get("process_names", []) or []:
                if process_name:
                    candidates.setdefault(process_name.casefold(), []).append(
                        (category_key, process_name)
                    )

        added = 0
        for folded, choices in sorted(candidates.items()):
            if folded in owner:
                continue
            category_key, process_name = min(
                choices, key=lambda choice: category_order(choice[0])
            )
            if category_key not in rules:
                incoming = incoming_rules.get(category_key, {})
                rules[category_key] = {
                    "display_name": incoming.get("display_name", ""),
                    "active_rule": incoming.get(
                        "active_rule", "interactive_required"
                    ),
                    "process_names": [],
                    "title_keywords": list(
                        incoming.get("title_keywords", []) or []
                    ),
                    "title_patterns": list(
                        incoming.get("title_patterns", []) or []
                    ),
                }
            rules[category_key]["process_names"].append(process_name)
            owner[folded] = category_key
            added += 1

        for key, rule in rules.items():
            _upsert_custom_rule(conn, key, rule)
        conn.commit()
        return added
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _split_rule_list(value: str | None) -> list[str]:
    return [item for item in (value or "").split("\n") if item]


def _upsert_custom_rule(conn, key: str, rule: dict) -> None:
    conn.execute(
        """
        INSERT INTO custom_rules (
            category_key, display_name, active_rule, process_names,
            title_keywords, title_patterns
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(category_key) DO UPDATE SET
            display_name = excluded.display_name,
            active_rule = excluded.active_rule,
            process_names = excluded.process_names,
            title_keywords = excluded.title_keywords,
            title_patterns = excluded.title_patterns
        """,
        (
            key,
            rule.get("display_name", ""),
            rule.get("active_rule", "interactive_required"),
            "\n".join(rule.get("process_names", []) or []),
            "\n".join(rule.get("title_keywords", []) or []),
            "\n".join(rule.get("title_patterns", []) or []),
        ),
    )


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
        title_patterns = rule.get("title_patterns", []) or list(
            base_match.get("title_patterns", []) or []
        )
        categories[key] = {
            "display_name": rule["display_name"]
            or base_category.get("display_name", key),
            "active_rule": rule["active_rule"]
            or base_category.get("active_rule", "interactive_required"),
            "match": {
                "process_names": rule["process_names"],
                "title_keywords": title_keywords,
                "title_patterns": title_patterns,
            },
        }


def delete_activity_logs_before(db_path: str, cutoff_date: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("DELETE FROM activity_logs WHERE date < ?", (cutoff_date,))
        conn.commit()
    finally:
        conn.close()
