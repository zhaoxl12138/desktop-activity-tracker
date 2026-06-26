from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QWidget

from desktop_activity_tracker import database
from desktop_activity_tracker.gui.pages.rule_config import RuleConfigPage


def _write_config(path: Path) -> None:
    config = {
        "categories": {
            "coding": {
                "display_name": "编程开发",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["Code.exe", "WindowsTerminal.exe"],
                    "title_keywords": ["VS Code", "Codex"],
                },
            },
            "video": {
                "display_name": "娱乐休闲",
                "active_rule": "passive_allowed",
                "match": {
                    "process_names": ["QyClient.exe"],
                    "title_keywords": ["爱奇艺"],
                },
            },
            "other": {
                "display_name": "其他",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
            "browser_general": {
                "display_name": "浏览器",
                "active_rule": "interactive_required",
                "match": {"process_names": ["chrome.exe"], "title_keywords": []},
            },
        }
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _select_category(page: RuleConfigPage, key: str) -> None:
    for row in range(page.cat_list.count()):
        item = page.cat_list.item(row)
        if item.data(Qt.UserRole) == key:
            page.cat_list.setCurrentRow(row)
            return
    raise AssertionError(f"category not found: {key}")


def test_rule_config_page_uses_rule_management_language():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.show()
        app.processEvents()

        texts = " ".join(label.text() for label in page.findChildren(QLabel) if label.text())
        assert "规则管理" in texts
        assert "计时策略" in texts
        assert "管理分类规则与计时策略" in texts


def test_rule_config_page_removes_legacy_strategy_summary_panels():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.show()
        app.processEvents()

        _select_category(page, "coding")
        app.processEvents()

        legacy_summary = getattr(page, "strategy_summary_frame", None)
        legacy_info = getattr(page, "strategy_info_frame", None)
        assert legacy_summary is None or not legacy_summary.isVisible()
        assert legacy_info is None or not legacy_info.isVisible()
        assert page.edit_rule.currentText() == "主动交互型"


def test_rule_config_page_match_hint_has_stable_info_bar_layout():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.show()
        app.processEvents()

        _select_category(page, "coding")
        app.processEvents()

        assert page.match_hint_frame.minimumHeight() >= 36
        assert page.match_hint.text().startswith("当前配置")
        assert not page.match_hint.wordWrap()
        assert page.match_hint.height() >= page.match_hint.minimumSizeHint().height()


def test_rule_config_page_container_styles_are_scoped_to_frames():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.resize(1346, 732)
        page.show()
        app.processEvents()

        containers = (
            page.category_panel,
            page.editor_panel,
            page.basic_card,
            page.strategy_card,
            page.match_card,
            page.match_hint_frame,
        )
        for frame in containers:
            assert frame.objectName()
            assert f"QFrame#{frame.objectName()}" in frame.styleSheet()


def test_rule_config_page_sections_do_not_overlap_at_runtime_height():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.resize(1346, 732)
        page.show()
        app.processEvents()

        _select_category(page, "coding")
        app.processEvents()

        required_widgets = (
            "basic_card",
            "strategy_card",
            "match_card",
            "action_bar",
        )
        assert all(hasattr(page, name) for name in required_widgets)

        assert not page.basic_card.geometry().intersects(page.match_card.geometry())
        assert not page.strategy_card.geometry().intersects(page.match_card.geometry())
        assert not page.match_card.geometry().intersects(page.action_bar.geometry())


def test_rule_editors_remain_inside_match_card():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        db_path = tmp_path / "usage.db"
        _write_config(config_path)
        database.init_db(str(db_path)).close()

        app = _app()
        page = RuleConfigPage(str(config_path), str(db_path))
        page.resize(1346, 732)
        page.show()
        app.processEvents()

        _select_category(page, "coding")
        app.processEvents()

        def is_inside(widget: QWidget, parent: QWidget) -> bool:
            top_left = widget.mapTo(parent, widget.rect().topLeft())
            bottom_right = widget.mapTo(parent, widget.rect().bottomRight())
            return parent.rect().contains(top_left) and parent.rect().contains(bottom_right)

        assert is_inside(page.edit_processes, page.match_card)
        assert is_inside(page.edit_keywords, page.match_card)
        assert page.edit_processes.height() >= 180
        assert page.edit_keywords.height() >= 180
