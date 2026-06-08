"""Runtime path and config helpers."""

from __future__ import annotations

import os

import yaml

from . import get_app_root

CONFIG_FILENAME = "config/config.yaml"
REPORTS_DIRNAME = "reports"
RELEASE_DIRNAME = "release"
RELEASE_EXE_NAME = "DayLens/DayLens.exe"


def resolve_config_path() -> str:
    return os.path.join(get_app_root(), CONFIG_FILENAME)


def resolve_reports_dir() -> str:
    from daylens import get_data_dir
    return os.path.join(get_data_dir(), REPORTS_DIRNAME)


def resolve_release_dir(app_root: str | None = None) -> str:
    base_dir = app_root or get_app_root()
    return os.path.join(base_dir, RELEASE_DIRNAME)


def resolve_release_exe_path(app_root: str | None = None) -> str:
    return os.path.join(resolve_release_dir(app_root), RELEASE_EXE_NAME)


def ensure_report_subdirs(reports_dir: str) -> None:
    for subdir in ("daily", "weekly", "monthly"):
        os.makedirs(os.path.join(reports_dir, subdir), exist_ok=True)


def load_config(config_path: str) -> dict:
    from .utils import generate_default_config, load_user_config

    if not os.path.exists(config_path):
        print(f"[INFO] 配置文件不存在，正在自动生成默认配置：{config_path}")
        generate_default_config(config_path)
    with open(config_path, "r", encoding="utf-8") as handle:
        config = yaml.safe_load(handle)

    user_config = load_user_config()
    for key in ("obsidian_output_path", "theme", "db_path"):
        if key in user_config and user_config[key]:
            config[key] = user_config[key]
    return config
