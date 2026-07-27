from __future__ import annotations

import copy
import os
import tempfile
from pathlib import Path

import pytest
import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QLabel, QMessageBox, QWidget

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


def _selected_key(page: RuleConfigPage) -> str | None:
    item = page.cat_list.currentItem()
    return item.data(Qt.UserRole) if item is not None else None


def _build_page(tmp_path: Path, *, worker=None) -> RuleConfigPage:
    app = _app()
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "usage.db"
    _write_config(config_path)
    database.init_db(str(db_path)).close()
    page = RuleConfigPage(str(config_path), str(db_path), worker)
    page._test_app = app
    page.show()
    app.processEvents()
    return page


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


def test_rule_rescan_is_queued_when_application_background_queue_is_available(tmp_path):
    class FakeQueue:
        def __init__(self):
            self.submissions = []

        def submit(self, key, task):
            self.submissions.append((key, task))
            return True

    app = _app()
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "usage.db"
    _write_config(config_path)
    database.init_db(str(db_path)).close()
    queue = FakeQueue()
    page = RuleConfigPage(str(config_path), str(db_path), background_tasks=queue)
    page.show()
    app.processEvents()

    page._rescan_apps()

    assert [key for key, _task in queue.submissions] == ["rules:scan"]
    assert page.btn_rescan.isEnabled() is False


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
        assert page.match_hint.wordWrap()
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


def test_rule_editor_tracks_dirty_fields_without_marking_category_load_dirty(tmp_path):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    _app().processEvents()

    assert page._dirty is False
    assert page.btn_save.isEnabled() is False

    for editor, mutate in (
        (page.edit_name, lambda: page.edit_name.setText("New name")),
        (page.edit_rule, lambda: page.edit_rule.setCurrentIndex(1)),
        (page.edit_processes, lambda: page.edit_processes.append("python.exe")),
        (page.edit_keywords, lambda: page.edit_keywords.append("Docs")),
    ):
        page._load_category("coding")
        _app().processEvents()
        assert page._dirty is False
        mutate()
        _app().processEvents()
        assert page._dirty is True, editor
        assert page.btn_save.isEnabled() is True


def test_dirty_category_switch_can_cancel_and_restore_old_editor(monkeypatch, tmp_path):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    page.edit_name.setText("Unsaved name")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Cancel
    )

    _select_category(page, "video")
    _app().processEvents()

    assert _selected_key(page) == "coding"
    assert page.edit_name.text() == "Unsaved name"
    assert page._dirty is True


def test_dirty_category_switch_can_discard_and_load_target(monkeypatch, tmp_path):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    original_name = page.categories["coding"]["display_name"]
    page.edit_name.setText("Discard me")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Discard
    )

    _select_category(page, "video")
    _app().processEvents()

    assert _selected_key(page) == "video"
    assert page._current_key == "video"
    assert page.categories["coding"]["display_name"] == original_name
    assert page.edit_name.text() == page.categories["video"]["display_name"]
    assert page._dirty is False


def test_dirty_category_switch_saves_before_loading_target(monkeypatch, tmp_path):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    page.edit_name.setText("Saved before switch")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Save
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    _select_category(page, "video")
    _app().processEvents()

    assert _selected_key(page) == "video"
    assert page.categories["coding"]["display_name"] == "Saved before switch"
    assert page._current_key == "video"
    assert page._dirty is False


def test_failed_save_rolls_back_live_state_and_preserves_metadata(
    monkeypatch, tmp_path
):
    class Worker:
        reload_count = 0

        def reload_classifier(self):
            self.reload_count += 1

    worker = Worker()
    page = _build_page(tmp_path, worker=worker)
    _select_category(page, "coding")
    page.categories["coding"]["match"]["title_patterns"] = ["docs\\.example"]
    page.categories["coding"]["match"]["title_patterns_mode"] = "inherit"
    original = page.categories["coding"].copy()
    original["match"] = page.categories["coding"]["match"].copy()
    page.edit_name.setText("Must roll back")

    def fail_save(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        fail_save,
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    assert page._save_current() is False
    assert page.categories["coding"] == original
    assert page.edit_name.text() == "Must roll back"
    assert page._dirty is True
    assert worker.reload_count == 0


def test_successful_save_preserves_title_patterns_and_unedited_modes(
    monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    page.categories["coding"]["match"].update(
        {
            "title_patterns": ["docs\\.example"],
            "process_names_mode": "inherit",
            "title_keywords_mode": "replace",
            "title_patterns_mode": "inherit",
        }
    )
    captured = {}
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda db_path, categories: captured.update(categories=categories),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    page.edit_keywords.append("New keyword")

    assert page._save_current() is True

    match = captured["categories"]["coding"]["match"]
    assert match["title_patterns"] == ["docs\\.example"]
    assert match["process_names_mode"] == "inherit"
    assert match["title_keywords_mode"] == "replace"
    assert match["title_patterns_mode"] == "inherit"
    assert page._dirty is False


def test_factory_markers_and_delete_protection_use_factory_config_only(
    monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    page.categories["focus"] = {
        "display_name": "Focus",
        "active_rule": "interactive_required",
        "match": {"process_names": [], "title_keywords": []},
    }
    page._populate_list()

    labels = {
        page.cat_list.item(row).data(Qt.UserRole): page.cat_list.item(row).text()
        for row in range(page.cat_list.count())
    }
    assert labels["coding"].startswith("🔒")
    assert labels["video"].startswith("🔒")
    assert labels["focus"].startswith("•")

    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args)
    )
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda *args, **kwargs: None,
    )

    _select_category(page, "coding")
    page._delete_current()
    assert "coding" in page.categories
    assert warnings

    _select_category(page, "focus")
    page._delete_current()
    assert "focus" not in page.categories


def test_add_failure_does_not_publish_category_or_reload_worker(
    monkeypatch, tmp_path
):
    class Worker:
        reload_count = 0

        def reload_classifier(self):
            self.reload_count += 1

    worker = Worker()
    page = _build_page(tmp_path, worker=worker)
    before = copy.deepcopy(page.categories)
    before_count = page.cat_list.count()
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    page._add_category()

    assert page.categories == before
    assert page.cat_list.count() == before_count
    assert worker.reload_count == 0


def test_delete_failure_does_not_remove_category_or_reload_worker(
    monkeypatch, tmp_path
):
    class Worker:
        reload_count = 0

        def reload_classifier(self):
            self.reload_count += 1

    worker = Worker()
    page = _build_page(tmp_path, worker=worker)
    page.categories["focus"] = {
        "display_name": "Focus",
        "active_rule": "interactive_required",
        "match": {"process_names": [], "title_keywords": []},
    }
    page._populate_list()
    _select_category(page, "focus")
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Yes
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    page._delete_current()

    assert "focus" in page.categories
    assert _selected_key(page) == "focus"
    assert worker.reload_count == 0


def test_rescan_failure_rolls_back_all_live_rules(monkeypatch, tmp_path):
    page = _build_page(tmp_path)
    before = copy.deepcopy(page.categories)
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.scan_installed_apps",
        lambda: ["ignored"],
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.classify_scanned_apps",
        lambda apps: {"coding": {"python.exe"}, "new_category": {"new.exe"}},
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    page._rescan_apps()

    assert page.categories == before
    assert "new_category" not in page.categories


def test_rescan_casefold_deduplicates_and_preserves_rule_metadata(
    monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    _select_category(page, "coding")
    page.categories["coding"]["match"].update(
        {
            "title_patterns": ["keep-me"],
            "title_patterns_mode": "inherit",
            "process_names_mode": "replace",
        }
    )
    captured = {}
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.scan_installed_apps",
        lambda: ["ignored"],
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.classify_scanned_apps",
        lambda apps: {"coding": {"code.exe", "PYTHON.EXE"}},
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda db_path, categories: captured.update(
            categories=copy.deepcopy(categories)
        ),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    page._rescan_apps()

    match = captured["categories"]["coding"]["match"]
    assert len([name for name in match["process_names"] if name.casefold() == "code.exe"]) == 1
    assert "PYTHON.EXE" in match["process_names"]
    assert match["title_patterns"] == ["keep-me"]
    assert match["title_patterns_mode"] == "inherit"
    assert match["process_names_mode"] == "replace"


def test_rule_editor_save_preserves_persisted_modes(monkeypatch, tmp_path):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "usage.db"
    _write_config(config_path)
    database.init_db(str(db_path)).close()
    database.save_custom_rules(
        str(db_path),
        {
            "coding": {
                "display_name": "Coding",
                "active_rule": "interactive_required",
                "process_names": ["Code.exe"],
                "process_names_mode": "inherit",
                "title_keywords": ["Codex"],
                "title_keywords_mode": "inherit",
                "title_patterns": ["docs\\.example"],
                "title_patterns_mode": "replace",
            }
        },
    )
    page = RuleConfigPage(str(config_path), str(db_path))
    page.show()
    _app().processEvents()
    _select_category(page, "coding")
    page.edit_name.setText("Updated")
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    assert page._save_current() is True

    stored = database.load_custom_rules(str(db_path))["coding"]
    assert stored["process_names_mode"] == "inherit"
    assert stored["title_keywords_mode"] == "inherit"
    assert stored["title_patterns_mode"] == "replace"
    assert stored["title_patterns"] == ["docs\\.example"]


def _prepare_dirty_rule_action(
    page: RuleConfigPage, action: str
) -> tuple[str, dict]:
    if action == "delete":
        page.categories["focus"] = {
            "display_name": "Focus",
            "active_rule": "interactive_required",
            "match": {"process_names": [], "title_keywords": []},
        }
        page._populate_list()
        _select_category(page, "focus")
    else:
        _select_category(page, "coding")
    selected_key = _selected_key(page)
    page.edit_name.setText("Unsaved action edit")
    return selected_key, copy.deepcopy(page.categories)


def _patch_rule_action_scan(monkeypatch, calls: dict) -> None:
    def scan():
        calls["scan"] += 1
        return ["ignored"]

    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.scan_installed_apps",
        scan,
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.classify_scanned_apps",
        lambda apps: {"coding": {"python.exe"}},
    )


def _run_rule_action(page: RuleConfigPage, action: str) -> None:
    {
        "add": page._add_category,
        "delete": page._delete_current,
        "rescan": page._rescan_apps,
    }[action]()


def _action_proceeded(
    page: RuleConfigPage, action: str, before: dict, calls: dict
) -> bool:
    if action == "add":
        return len(page.categories) == len(before) + 1
    if action == "delete":
        return "focus" not in page.categories
    return calls["scan"] == 1 and "python.exe" in {
        process.casefold()
        for process in page.categories["coding"]["match"]["process_names"]
    }


@pytest.mark.parametrize("action", ["add", "delete", "rescan"])
def test_dirty_rule_action_cancel_preserves_editor_and_skips_action(
    action, monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    selected_key, before = _prepare_dirty_rule_action(page, action)
    calls = {"scan": 0}
    _patch_rule_action_scan(monkeypatch, calls)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Cancel
    )

    _run_rule_action(page, action)

    assert page.categories == before
    assert _selected_key(page) == selected_key
    assert page.edit_name.text() == "Unsaved action edit"
    assert page._dirty is True
    assert calls["scan"] == 0


@pytest.mark.parametrize("action", ["add", "delete", "rescan"])
def test_dirty_rule_action_failed_save_preserves_editor_and_skips_action(
    action, monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    selected_key, before = _prepare_dirty_rule_action(page, action)
    calls = {"scan": 0}
    _patch_rule_action_scan(monkeypatch, calls)
    monkeypatch.setattr(
        QMessageBox, "question", lambda *args, **kwargs: QMessageBox.Save
    )
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("disk full")),
    )
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: None)

    _run_rule_action(page, action)

    assert page.categories == before
    assert _selected_key(page) == selected_key
    assert page.edit_name.text() == "Unsaved action edit"
    assert page._dirty is True
    assert calls["scan"] == 0


@pytest.mark.parametrize("action", ["add", "delete", "rescan"])
def test_dirty_rule_action_save_success_commits_edit_then_proceeds(
    action, monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    selected_key, before = _prepare_dirty_rule_action(page, action)
    calls = {"scan": 0, "saved": []}
    _patch_rule_action_scan(monkeypatch, calls)

    def answer(*args, **kwargs):
        if args[1] == "未保存的修改":
            return QMessageBox.Save
        if args[1] == "确认删除":
            return QMessageBox.Yes
        raise AssertionError(args[1])

    monkeypatch.setattr(QMessageBox, "question", answer)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda db_path, categories: calls["saved"].append(
            copy.deepcopy(categories)
        ),
    )

    _run_rule_action(page, action)

    assert calls["saved"][0][selected_key]["display_name"] == "Unsaved action edit"
    assert _action_proceeded(page, action, before, calls)


@pytest.mark.parametrize("action", ["add", "delete", "rescan"])
def test_dirty_rule_action_discard_explicitly_then_proceeds(
    action, monkeypatch, tmp_path
):
    page = _build_page(tmp_path)
    selected_key, before = _prepare_dirty_rule_action(page, action)
    calls = {"scan": 0, "saved": []}
    _patch_rule_action_scan(monkeypatch, calls)

    def answer(*args, **kwargs):
        if args[1] == "未保存的修改":
            return QMessageBox.Discard
        if args[1] == "确认删除":
            return QMessageBox.Yes
        raise AssertionError(args[1])

    monkeypatch.setattr(QMessageBox, "question", answer)
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "desktop_activity_tracker.gui.pages.rule_config.save_rule_categories",
        lambda db_path, categories: calls["saved"].append(
            copy.deepcopy(categories)
        ),
    )

    _run_rule_action(page, action)

    assert _action_proceeded(page, action, before, calls)
    if selected_key in page.categories:
        assert page.categories[selected_key]["display_name"] != "Unsaved action edit"
