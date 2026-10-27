from __future__ import annotations

from pathlib import Path

import yaml

from desktop_activity_tracker.services import (
    category_stats_service,
    rules_service,
    shell_service,
    software_stats_service,
)
from desktop_activity_tracker.utils import (
    _DEFAULT_CATEGORIES,
    ENTERTAINMENT_CATEGORY_KEYS,
    WORK_CATEGORY_KEYS,
    normalize_category_display_name,
    normalize_rule_category_display_name,
)
from desktop_activity_tracker import timeline
from desktop_activity_tracker.repositories import stats_repository
from desktop_activity_tracker.services import daily_goal_service, dashboard_service


def test_statistics_consumers_share_registry_derived_category_groups():
    assert dashboard_service.WORK_KEYS == WORK_CATEGORY_KEYS
    assert dashboard_service.ENTERTAINMENT_KEYS == ENTERTAINMENT_CATEGORY_KEYS
    assert stats_repository.WORK_CATEGORY_KEYS == WORK_CATEGORY_KEYS
    assert timeline.WORK_CATS == WORK_CATEGORY_KEYS
    assert timeline.ENTERTAINMENT_CATS == ENTERTAINMENT_CATEGORY_KEYS
    assert daily_goal_service._WORK_CATEGORIES == WORK_CATEGORY_KEYS


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
    assert summary["total_label"].startswith("今日有效时间总计：")


def test_tray_calls_effective_time_effective_instead_of_active(monkeypatch):
    monkeypatch.setattr(
        shell_service,
        "load_shell_summary",
        lambda _db_path: {
            "effective_seconds": 3_600,
            "work_seconds": 1_800,
            "entertainment_seconds": 600,
            "social_seconds": 300,
        },
    )

    tooltip = shell_service.build_tray_tooltip("dummy.db", paused=False)

    assert "有效时间: 1时" in tooltip
    assert "活跃时间" not in tooltip


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


def test_empty_custom_keywords_keep_builtin_keywords(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "categories:\n  browser_general:\n    display_name: 浏览器\n    active_rule: interactive_required\n    match:\n      process_names: [chrome.exe]\n      title_keywords: [Google, 搜索]\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        category_stats_service.database,
        "load_custom_rules",
        lambda db_path: {
            "browser_general": {
                "display_name": "浏览器",
                "active_rule": "interactive_required",
                "process_names": ["chrome.exe"],
                "title_keywords": [],
            }
        },
    )

    loaded = __import__("desktop_activity_tracker.services.rules_service", fromlist=["load_rule_categories"]).load_rule_categories(
        str(config_path), "dummy.db"
    )
    assert loaded["browser_general"]["match"]["title_keywords"] == ["Google", "搜索"]


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
    assert categories["video"]["display_name"] == "视频与游戏"


def test_rule_entertainment_names_distinguish_legacy_duplicates_and_keep_custom_names():
    assert normalize_rule_category_display_name("gaming", "娱乐休闲") == "游戏娱乐"
    assert normalize_rule_category_display_name("video", "娱乐休闲") == "视频娱乐"
    assert normalize_rule_category_display_name("video", "视频与游戏") == "视频与游戏"
    assert normalize_rule_category_display_name("video", "影音娱乐") == "影音娱乐"
    assert normalize_rule_category_display_name("video", "游戏娱乐") == "游戏娱乐"
    assert normalize_rule_category_display_name("gaming", "视频娱乐") == "视频娱乐"
    assert normalize_rule_category_display_name("gaming", "我玩的游戏") == "我玩的游戏"
    assert normalize_rule_category_display_name("video", "我的影院") == "我的影院"


def test_factory_entertainment_rule_names_and_policies_are_distinct():
    assert _DEFAULT_CATEGORIES["gaming"]["display_name"] == "游戏娱乐"
    assert _DEFAULT_CATEGORIES["gaming"]["active_rule"] == "interactive_required"
    assert _DEFAULT_CATEGORIES["video"]["display_name"] == "视频娱乐"
    assert _DEFAULT_CATEGORIES["video"]["active_rule"] == "passive_allowed"
    root = Path(__file__).resolve().parents[1]
    for filename in ("config.yaml", "config.example.yaml"):
        categories = yaml.safe_load((root / "config" / filename).read_text(encoding="utf-8"))["categories"]
        assert categories["gaming"]["display_name"] == "游戏娱乐"
        assert categories["gaming"]["active_rule"] == "interactive_required"
        assert categories["video"]["display_name"] == "视频娱乐"
        assert categories["video"]["active_rule"] == "passive_allowed"
