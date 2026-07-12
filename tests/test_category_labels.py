from __future__ import annotations

from pathlib import Path

import yaml

from desktop_activity_tracker.services import category_stats_service, rules_service, software_stats_service
from desktop_activity_tracker.utils import normalize_category_display_name


def test_normalize_category_display_name_maps_new_global_labels():
    assert normalize_category_display_name("coding", "学习/工作") == "工作学习"
    assert normalize_category_display_name("reading", "阅读学习") == "工作学习"
    assert normalize_category_display_name("video", "视频娱乐") == "娱乐休闲"
    assert normalize_category_display_name("video", "视频与游戏") == "娱乐休闲"
    assert normalize_category_display_name("social", "社交通讯") == "社交通讯"
    assert normalize_category_display_name("browser_general", "浏览器其他") == "浏览器"


def test_category_summary_uses_normalized_labels(monkeypatch):
    monkeypatch.setattr(
        category_stats_service.database,
        "query_date_stats",
        lambda db_path, today: {
            "by_category": [
                {"category_key": "coding", "category_name": "学习/工作", "effective_seconds": 1200},
                {"category_key": "video", "category_name": "视频娱乐", "effective_seconds": 600},
                {"category_key": "social", "category_name": "社交通讯", "effective_seconds": 300},
            ]
        },
    )

    summary = category_stats_service.load_category_summary("dummy.db")
    names = [item["category_name"] for item in summary["categories"]]
    assert names == ["工作学习", "娱乐休闲", "社交通讯"]


def test_category_summary_orders_by_effective_time_descending(monkeypatch):
    monkeypatch.setattr(
        category_stats_service.database,
        "query_date_stats",
        lambda db_path, today: {
            "by_category": [
                {"category_key": "social", "category_name": "social", "effective_seconds": 3000},
                {"category_key": "coding", "category_name": "coding", "effective_seconds": 1200},
                {"category_key": "video", "category_name": "video", "effective_seconds": 600},
            ]
        },
    )

    summary = category_stats_service.load_category_summary("dummy.db")
    assert [item["category_key"] for item in summary["categories"]] == ["social", "work", "entertainment"]


def test_software_rows_use_normalized_labels(monkeypatch):
    monkeypatch.setattr(
        software_stats_service.database,
        "query_date_stats",
        lambda db_path, today: {
            "totals": {"effective_seconds": 1800},
            "by_app": [
                {"process_name": "chrome.exe", "category_key": "video", "category_name": "视频娱乐", "effective_seconds": 900},
            ],
            "by_app_detail": [
                {"process_name": "chrome.exe", "window_title": "Test", "effective_seconds": 900},
            ],
        },
    )

    rows = software_stats_service.load_software_rows("dummy.db", {})
    assert rows[0]["category_name"] == "娱乐休闲"


def test_rule_categories_hide_idle_and_normalize_names(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "categories": {
                    "browser_general": {
                        "display_name": "浏览器其他",
                        "active_rule": "interactive_required",
                        "match": {"process_names": [], "title_keywords": []},
                    },
                    "video": {
                        "display_name": "视频与游戏",
                        "active_rule": "passive_allowed",
                        "match": {"process_names": [], "title_keywords": []},
                    },
                }
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        rules_service.database,
        "load_custom_rules",
        lambda db_path: {
            "idle": {
                "display_name": "挂机",
                "active_rule": "interactive_required",
                "process_names": [],
                "title_keywords": [],
            }
        },
    )

    categories = rules_service.load_rule_categories(str(config_path), "dummy.db")

    assert "idle" not in categories
    assert categories["browser_general"]["display_name"] == "浏览器"
    assert categories["video"]["display_name"] == "娱乐休闲"
