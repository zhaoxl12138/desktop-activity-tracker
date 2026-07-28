from pathlib import Path

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
