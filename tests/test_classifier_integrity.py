from copy import deepcopy
from pathlib import Path
import re

import pytest
import yaml

from desktop_activity_tracker.classifier import Classifier


def _write_config(path: Path) -> None:
    config = {
        "categories": {
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": [],
                    "title_keywords": ["YouTube", "bilibili"],
                },
            },
            "coding": {
                "display_name": "编程开发",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": [],
                    "title_keywords": ["GitHub"],
                },
            },
            "browser_general": {
                "display_name": "浏览器",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["chrome.exe", "360ChromeX.exe"],
                    "title_keywords": ["Chrome", "浏览器", "新标签页"],
                },
            },
            "other": {
                "display_name": "其他",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        }
    }
    path.write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )


def test_chrome_youtube_uses_content_before_browser_fallback(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "YouTube - Google Chrome",
    )

    assert result["category_key"] == "video"


def test_360_bilibili_uses_content_before_browser_fallback(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    result = Classifier(str(config_path)).classify(
        "360ChromeX.exe",
        "凡人修仙传 - bilibili - 360极速浏览器X",
    )

    assert result["category_key"] == "video"


def test_chrome_github_uses_coding_content_rule(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "GitHub - Google Chrome",
    )

    assert result["category_key"] == "coding"


def test_chrome_new_tab_falls_back_to_browser_general(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)

    result = Classifier(str(config_path)).classify(
        "chrome.exe",
        "新标签页 - Google Chrome",
    )

    assert result["category_key"] == "browser_general"


def test_sourceinsight4_process_is_work_learning(tmp_path: Path):
    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    config["categories"]["coding"]["match"]["process_names"] = [
        "sourceinsight4.exe"
    ]
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )

    result = Classifier(str(config_path)).classify(
        "SourceInsight4.exe",
        "kernel Project",
    )

    assert result["category_key"] == "coding"


def _fingerprint_config() -> dict:
    return {
        "theme": "dark",
        "tracker": {"sample_interval_seconds": 1},
        "categories": {
            "coding": {
                "display_name": "Coding",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["Code.exe", "PYCHARM64.EXE"],
                    "title_keywords": ["GitHub", "Stack Overflow"],
                    "title_patterns": [r"\bissue #\d+\b", r"docs\.\w+"],
                },
            },
            "video": {
                "display_name": "Video",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": ["vlc.exe"],
                    "title_keywords": ["YouTube"],
                    "title_patterns": [r"episode\s+\d+"],
                },
            },
        },
    }


def test_rule_fingerprint_is_stable_for_equivalent_rule_mappings():
    config_a = _fingerprint_config()
    config_b = {
        "categories": {
            "video": {
                "active_rule": "passive_allowed",
                "match": {
                    "title_patterns": [" episode\\s+\\d+ ", r"episode\s+\d+"],
                    "title_keywords": [" youtube ", "YOUTUBE"],
                    "process_names": [" VLC.EXE ", "vlc.exe"],
                },
                "display_name": "Entertainment",
            },
            "coding": {
                "active_rule": "interactive_required",
                "match": {
                    "title_patterns": [" docs\\.\\w+ ", r"\bissue #\d+\b", r"docs\.\w+"],
                    "title_keywords": [" stack overflow ", "GITHUB", "github"],
                    "process_names": [" pycharm64.exe ", "CODE.EXE", "code.exe"],
                },
                "display_name": "Development",
            },
        },
        "theme": "light",
        "tracker": {"sample_interval_seconds": 60},
    }

    fingerprint = Classifier.rule_fingerprint(config_a)

    assert fingerprint == Classifier.rule_fingerprint(config_b)
    assert re.fullmatch(r"rules-[0-9a-f]{12}", fingerprint)


@pytest.mark.parametrize(
    ("field", "changed_value"),
    [
        ("active_rule", "passive_allowed"),
        ("process_names", ["Code.exe", "zed.exe"]),
        ("title_keywords", ["GitHub", "GitLab"]),
        ("title_patterns", [r"\bissue #\d+\b", r"pull request #\d+"]),
    ],
)
def test_rule_fingerprint_changes_with_effective_rule_content(field, changed_value):
    config = _fingerprint_config()
    changed = deepcopy(config)
    if field == "active_rule":
        changed["categories"]["coding"][field] = changed_value
    else:
        changed["categories"]["coding"]["match"][field] = changed_value

    assert Classifier.rule_fingerprint(config) != Classifier.rule_fingerprint(changed)


def test_rule_fingerprint_ignores_unrelated_and_display_only_settings():
    config = _fingerprint_config()
    changed = deepcopy(config)
    changed["theme"] = "solarized"
    changed["tracker"] = {"idle_threshold_seconds": 999}
    changed["categories"]["coding"]["display_name"] = "Software engineering"

    assert Classifier.rule_fingerprint(config) == Classifier.rule_fingerprint(changed)


def test_classifier_versions_final_rules_after_custom_merge(tmp_path: Path, monkeypatch):
    from desktop_activity_tracker import database

    config_path = tmp_path / "config.yaml"
    _write_config(config_path)
    config_before_merge = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    db_path = tmp_path / "usage.db"
    db_path.touch()

    def merge_custom_rule(config, _db_path):
        config["categories"]["coding"]["match"]["process_names"] = ["custom.exe"]

    monkeypatch.setattr(database, "merge_custom_rules", merge_custom_rule)

    classifier = Classifier(str(config_path), str(db_path))

    assert classifier.classification_version == Classifier.rule_fingerprint(classifier.config)
    assert classifier.classification_version != Classifier.rule_fingerprint(config_before_merge)
