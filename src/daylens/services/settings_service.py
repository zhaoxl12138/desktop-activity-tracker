"""Settings-related persistence and OS integration helpers."""

from __future__ import annotations

import os
import copy
from datetime import datetime, timedelta

import yaml

from .. import database, get_app_root
from ..runtime import resolve_release_exe_path
from ..utils import load_user_config, save_user_config


def normalize_database_path(path: str) -> str:
    """Return an absolute database path rooted at the DayLens app directory."""
    expanded = os.path.expandvars(os.path.expanduser(path.strip()))
    if not expanded:
        raise ValueError("数据库路径不能为空")
    if not os.path.isabs(expanded):
        expanded = os.path.join(get_app_root(), expanded)
    return os.path.abspath(expanded)


def load_page_config(config_path: str, db_path: str) -> dict:
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            config = yaml.safe_load(handle) or {}
    except (FileNotFoundError, yaml.YAMLError):
        config = {}

    if not isinstance(config, dict):
        config = {}

    user_config = load_user_config()
    if isinstance(user_config, dict):
        for key in ("obsidian_output_path", "theme", "db_path"):
            if key in user_config and user_config[key]:
                config[key] = user_config[key]

    effective_db_path = config.get("db_path", db_path)
    database.merge_db_settings(config, effective_db_path)
    return config


def save_page_config(
    *,
    config_path: str,
    db_path: str,
    config: dict,
    sample_interval: int,
    idle_threshold: int,
    startup_enabled: bool,
    new_db_path: str,
    obsidian_output_path: str,
) -> dict:
    normalized_db_path = normalize_database_path(new_db_path)

    updated = copy.deepcopy(config)
    updated["sample_interval_seconds"] = sample_interval
    updated["idle_threshold_seconds"] = idle_threshold
    updated["db_path"] = normalized_db_path
    updated["startup_enabled"] = startup_enabled
    updated["obsidian_output_path"] = obsidian_output_path
    updated["theme"] = updated.get("theme", "dark")

    tracker = updated.setdefault("tracker", {})
    tracker["sample_interval_seconds"] = sample_interval
    tracker["idle_threshold_seconds"] = idle_threshold

    effective_db_path = updated.get("db_path", db_path)
    connection = database.init_db(effective_db_path)
    database.close_db(connection)

    database.save_settings(effective_db_path, updated)
    persisted = {
        key: updated[key]
        for key in ("obsidian_output_path", "theme", "db_path")
        if key in updated and updated[key]
    }
    remove_keys = {"obsidian_output_path"} if not obsidian_output_path else set()
    save_user_config(persisted, remove_keys=remove_keys)
    return updated


def get_startup_link_path() -> str:
    startup_dir = os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup")
    return os.path.join(startup_dir, "DayLens.lnk")


def get_release_exe_path() -> str:
    return resolve_release_exe_path(get_app_root())


def toggle_startup_shortcut(enable: bool, exe_path: str, link_path: str | None = None) -> None:
    link_path = link_path or get_startup_link_path()
    if enable:
        if not os.path.isfile(exe_path):
            raise FileNotFoundError(exe_path)
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortcut(link_path)
        shortcut.TargetPath = exe_path
        shortcut.WorkingDirectory = os.path.dirname(exe_path)
        shortcut.Description = "DayLens - 个人数字行为分析系统"
        shortcut.WindowStyle = 7
        shortcut.Save()
        return

    try:
        os.remove(link_path)
    except OSError:
        pass


def cleanup_old_logs(db_path: str, days: int = 30) -> str:
    cutoff = (
        datetime.now().replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days)
    ).strftime("%Y-%m-%d")
    database.delete_activity_logs_before(db_path, cutoff)
    return cutoff
