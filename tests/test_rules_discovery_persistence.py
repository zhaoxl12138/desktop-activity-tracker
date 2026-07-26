from __future__ import annotations

import pytest
import yaml

from daylens import database
from daylens.app_scanner import (
    KNOWN_APPS,
    _extract_exe_from_path,
    classify_scanned_apps,
)
from daylens.services import rules_service


def _factory_config() -> dict:
    return {
        "categories": {
            "office": {
                "display_name": "办公套件",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["excel.exe"],
                    "title_keywords": ["工作簿"],
                    "title_patterns": [r"\.xlsx$"],
                },
            },
            "reading": {
                "display_name": "阅读学习",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["zotero.exe"],
                    "title_keywords": ["论文"],
                    "title_patterns": [r"第\d+章", r"\.pdf$"],
                },
            },
            "tools": {
                "display_name": "系统工具",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": [],
                    "title_keywords": [],
                    "title_patterns": [],
                },
            },
        }
    }


def test_custom_rules_round_trip_title_patterns_and_inherit_factory_lists(tmp_path):
    db_path = str(tmp_path / "usage.db")
    database.init_db(db_path).close()
    database.save_custom_rules(
        db_path,
        {
            "reading": {
                "display_name": "我的阅读",
                "active_rule": "passive_allowed",
                "process_names": ["Calibre.exe"],
                "title_keywords": ["我的关键词"],
                "title_patterns": [],
            }
        },
    )

    stored = database.load_custom_rules(db_path)
    assert stored["reading"]["title_patterns"] == []

    config = _factory_config()
    database.merge_custom_rules(config, db_path)
    reading = config["categories"]["reading"]
    assert reading["display_name"] == "我的阅读"
    assert reading["active_rule"] == "passive_allowed"
    assert reading["match"]["title_keywords"] == ["我的关键词"]
    assert reading["match"]["title_patterns"] == [r"第\d+章", r"\.pdf$"]


def test_nonempty_custom_patterns_override_factory_patterns(tmp_path):
    db_path = str(tmp_path / "usage.db")
    database.init_db(db_path).close()
    database.save_custom_rules(
        db_path,
        {
            "reading": {
                "display_name": "阅读学习",
                "active_rule": "interactive_required",
                "process_names": [],
                "title_keywords": [],
                "title_patterns": [r"自定义-\d+"],
            }
        },
    )
    config = _factory_config()

    database.merge_custom_rules(config, db_path)

    match = config["categories"]["reading"]["match"]
    assert match["title_keywords"] == ["论文"]
    assert match["title_patterns"] == [r"自定义-\d+"]


def test_rule_editor_service_round_trips_title_patterns(tmp_path):
    db_path = str(tmp_path / "usage.db")
    config_path = tmp_path / "config.yaml"
    database.init_db(db_path).close()
    config_path.write_text(
        yaml.safe_dump(_factory_config(), allow_unicode=True),
        encoding="utf-8",
    )
    categories = rules_service.load_rule_categories(str(config_path), db_path)
    categories["reading"]["match"]["title_patterns"] = [r"用户正则-\d+"]

    rules_service.save_rule_categories(db_path, categories)

    assert database.load_custom_rules(db_path)["reading"]["title_patterns"] == [
        r"用户正则-\d+"
    ]


def test_scanned_rules_merge_without_deleting_custom_data_and_existing_owner_wins(tmp_path):
    db_path = str(tmp_path / "usage.db")
    database.init_db(db_path).close()
    database.save_custom_rules(
        db_path,
        {
            "reading": {
                "display_name": "我的阅读",
                "active_rule": "passive_allowed",
                "process_names": ["Shared.EXE", "private-reader.exe"],
                "title_keywords": ["用户阅读词"],
                "title_patterns": [r"用户-\d+"],
            },
            "private": {
                "display_name": "私人分类",
                "active_rule": "interactive_required",
                "process_names": ["secret.exe"],
                "title_keywords": ["保留"],
                "title_patterns": ["保留.*"],
            },
        },
    )

    count = rules_service.save_scanned_rules(
        db_path,
        _factory_config(),
        {
            "office": {"shared.exe", "EXCEL.EXE", "fresh-conflict.exe"},
            "tools": {"shared.exe", "utools.exe", "FRESH-CONFLICT.EXE"},
        },
    )

    assert count == 3
    stored = database.load_custom_rules(db_path)
    assert stored["reading"] == {
        "display_name": "我的阅读",
        "active_rule": "passive_allowed",
        "process_names": ["Shared.EXE", "private-reader.exe"],
        "title_keywords": ["用户阅读词"],
        "title_patterns": [r"用户-\d+"],
    }
    assert stored["private"]["process_names"] == ["secret.exe"]
    assert stored["office"]["process_names"] == ["EXCEL.EXE", "fresh-conflict.exe"]
    assert stored["tools"]["process_names"] == ["utools.exe"]
    all_processes = [
        process.casefold()
        for rule in stored.values()
        for process in rule["process_names"]
    ]
    assert all_processes.count("shared.exe") == 1


def test_wizard_merge_uses_factory_metadata_and_marks_complete_after_success(tmp_path):
    db_path = str(tmp_path / "usage.db")
    database.init_db(db_path).close()
    database.save_custom_rules(
        db_path,
        {
            "private": {
                "display_name": "私人分类",
                "active_rule": "passive_allowed",
                "process_names": ["keep.exe"],
                "title_keywords": ["保留"],
                "title_patterns": ["保留.*"],
            }
        },
    )

    rules_service.save_wizard_classifications(
        db_path,
        {"Excel.EXE": "office", "ignored.exe": None},
        _factory_config(),
    )

    stored = database.load_custom_rules(db_path)
    assert stored["private"]["process_names"] == ["keep.exe"]
    assert stored["office"]["display_name"] == "办公套件"
    assert stored["office"]["active_rule"] == "interactive_required"
    assert stored["office"]["process_names"] == ["Excel.EXE"]
    assert database.load_settings(db_path)["wizard_completed"] == "true"


def test_wizard_does_not_mark_complete_when_rule_merge_fails(tmp_path, monkeypatch):
    db_path = str(tmp_path / "usage.db")
    database.init_db(db_path).close()

    def fail(*_args, **_kwargs):
        raise RuntimeError("write failed")

    monkeypatch.setattr(rules_service.database, "merge_discovered_rules", fail)
    with pytest.raises(RuntimeError, match="write failed"):
        rules_service.save_wizard_classifications(
            db_path, {"Excel.EXE": "office"}, _factory_config()
        )

    assert database.load_settings(db_path) is None


def test_known_app_keys_are_lowercase_and_office_apps_are_consistent():
    assert all(key == key.lower() for key in KNOWN_APPS)
    assert KNOWN_APPS["utools.exe"] == "tools"
    assert KNOWN_APPS["powertoys.exe"] == "tools"
    for process in (
        "wps.exe",
        "wpp.exe",
        "et.exe",
        "winword.exe",
        "excel.exe",
        "powerpnt.exe",
        "outlook.exe",
    ):
        assert KNOWN_APPS[process] == "office"


def test_scanner_lookup_is_case_insensitive_but_preserves_process_spelling():
    classified = classify_scanned_apps(
        {"PowerToys.EXE": None, "OUTLOOK.EXE": None, "WPS.EXE": None}
    )

    assert classified["tools"] == {"PowerToys.EXE"}
    assert classified["office"] == {"OUTLOOK.EXE", "WPS.EXE"}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r'"C:\Program Files\Example\Example.exe" --remove', "example.exe"),
        (r"C:\Program Files\Example\Example.exe /uninstall", "example.exe"),
        (r'"C:\Program Files\Example\Example.exe",0', "example.exe"),
        (r"C:\Tools\PowerToys.EXE, -2", "powertoys.exe"),
        (r'"C:\Tools\update.exe" --silent', None),
        (r"C:\Tools\uninstall-helper.exe /S", None),
    ],
)
def test_registry_command_parser_extracts_main_executable(raw, expected):
    assert _extract_exe_from_path(raw) == expected
