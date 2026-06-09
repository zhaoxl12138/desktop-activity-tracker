"""Startup-time database and rule bootstrap helpers."""

from __future__ import annotations

from .. import database


def prepare_runtime_config(config: dict) -> tuple[dict, str]:
    db_path = database.get_db_path(config)
    database.init_db(db_path)
    database.init_shared_read_conn(db_path)
    database.merge_db_settings(config, db_path)
    database.merge_custom_rules(config, db_path)
    return config, db_path


def load_bootstrap_state(db_path: str) -> tuple[dict, dict]:
    settings = database.load_settings(db_path) or {}
    custom_rules = database.load_custom_rules(db_path)
    return settings, custom_rules


def refresh_custom_rules(config: dict, db_path: str) -> None:
    database.merge_custom_rules(config, db_path)


def shutdown_runtime_state() -> None:
    database.close_shared_read_conn()
