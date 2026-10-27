import copy
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog
from tests.test_rule_config_page import _build_page, _select_category, _app
from daylens.classifier import Classifier


def test_advanced_defaults_collapsed_and_never_clears_existing_rules(tmp_path):
    page = _build_page(tmp_path)
    try:
        _select_category(page, 'coding')
        before = copy.deepcopy(page.categories)
        assert page.advanced_panel.isHidden()
        assert not page.edit_keywords.isVisible()
        assert not page.edit_rule.isVisible()
        assert page.applications_list.isVisible()
        assert page.applications_list.count() == 2
        selected = page.cat_list.currentItem()
        assert 'coding' not in selected.text()
        assert 'coding' in selected.toolTip()
        page.advanced_toggle.click()
        _app().processEvents()
        assert page.edit_keywords.isVisible()
        assert page.edit_rule.isVisible()
        page.advanced_toggle.click()
        assert not page._dirty
        assert page.categories == before
    finally:
        page.close()


def test_application_add_remove_changes_draft_only_and_preserves_keywords(tmp_path):
    page = _build_page(tmp_path)
    try:
        _select_category(page, 'coding')
        before = copy.deepcopy(page.categories)
        page._append_application('example.exe')
        assert page._dirty
        assert page.applications_list.count() == 3
        assert page.applications_list.currentItem().text() == 'example.exe'
        assert '3 个应用' in page.match_hint.text()
        page._append_application('EXAMPLE.EXE')
        assert page.applications_list.count() == 3
        page.applications_list.setCurrentRow(2)
        page._remove_applications()
        assert page.applications_list.count() == 2
        assert page.categories == before
        assert page.edit_keywords.toPlainText() == 'VS Code\nCodex'
    finally:
        page.close()


def test_draft_testing_accepts_no_title_and_does_not_persist(tmp_path):
    page = _build_page(tmp_path)
    try:
        _select_category(page, 'coding')
        page._append_application('new-work.exe')
        persisted = Classifier(page.config_path, page.db_path).classify('new-work.exe', '')
        assert persisted['category_key'] == 'other'
        result = page._test_draft('new-work.exe')
        assert result['category_key'] == 'coding'
        assert Classifier(page.config_path, page.db_path).classify('new-work.exe', '') == persisted
        assert page._dirty
    finally:
        page.close()


def test_memory_classifier_uses_existing_engine_without_mutating_input():
    config = {'categories': {'reading': {'display_name':'学习', 'active_rule':'interactive_required',
              'match': {'process_names':['reader.exe'], 'title_keywords':['学习中心']}},
              'other': {'display_name':'其他', 'active_rule':'interactive_required', 'match': {}}}}
    before = copy.deepcopy(config)
    classifier = Classifier(config=config)
    config['categories']['reading']['match']['process_names'].clear()
    assert classifier.classify('reader.exe','')['category_key'] == 'reading'
    assert classifier.classify('chrome.exe','学习中心')['category_key'] == 'reading'
    assert classifier.config == before


def test_application_dialog_has_optional_title_and_accepts_selected_process():
    from daylens.gui.widgets.rule_application_dialog import RuleApplicationDialog
    _app()
    dialog = RuleApplicationDialog(['Code.exe','chrome.exe'], testing=True)
    dialog.application.setCurrentText('Code.exe')
    assert dialog.title.text() == ''
    dialog.accept()
    assert dialog.result() == QDialog.Accepted
    assert dialog.selected_process() == 'Code.exe'
    assert dialog.selected_title() == ''
    add = RuleApplicationDialog(['Code.exe'])
    assert add.title.isHidden()
    add.application.setCurrentText('')
    add.accept()
    assert add.result() != QDialog.Accepted


def test_collapsed_save_keeps_title_patterns_and_timing_policy(tmp_path, monkeypatch):
    from desktop_activity_tracker import database
    from PySide6.QtWidgets import QMessageBox
    page = _build_page(tmp_path)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    try:
        _select_category(page, 'video')
        page.categories['video']['match']['title_patterns'] = ['第\\d+集']
        page._load_category('video')
        page._append_application('new-player.exe')
        assert page.advanced_panel.isHidden()
        assert page._save_current()
        saved = database.load_custom_rules(page.db_path)['video']
        assert saved['title_keywords'] == ['爱奇艺']
        assert saved['title_patterns'] == ['第\\d+集']
        assert saved['active_rule'] == 'passive_allowed'
        assert 'new-player.exe' in saved['process_names']
    finally:
        page.close()


def test_application_filter_does_not_mark_draft_dirty(tmp_path):
    page = _build_page(tmp_path)
    try:
        _select_category(page, 'coding')
        page.application_search.setText('terminal')
        assert page.applications_list.item(0).isHidden()
        assert not page.applications_list.item(1).isHidden()
        assert not page._dirty
    finally:
        page.close()


def test_preview_matches_saved_existing_process_ownership(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    page = _build_page(tmp_path)
    messages = []
    monkeypatch.setattr(QMessageBox, 'information', lambda _parent, _title, message: messages.append(message))
    try:
        _select_category(page, 'coding')
        page._append_application('QyClient.exe')
        preview = page._test_draft('QyClient.exe')
        assert preview['category_key'] == 'video'
        assert page._save_current()
        actual = Classifier(page.config_path, page.db_path).classify('QyClient.exe', '')
        assert preview == actual == page._test_draft('QyClient.exe')
        assert 'QyClient.exe' not in page.edit_processes.toPlainText()
        assert 'QyClient.exe' in messages[-1]
    finally:
        page.close()


def test_editing_inherited_lists_replaces_only_edited_fields(tmp_path, monkeypatch):
    from desktop_activity_tracker import database
    from desktop_activity_tracker.services.rules_service import load_rule_categories
    from PySide6.QtWidgets import QMessageBox
    page = _build_page(tmp_path)
    monkeypatch.setattr(QMessageBox, 'information', lambda *args: None)
    try:
        database.save_custom_rules(page.db_path, {'coding': {'display_name':'编程开发',
            'active_rule':'interactive_required', 'process_names':[], 'process_names_mode':'inherit',
            'title_keywords':[], 'title_keywords_mode':'inherit', 'title_patterns_mode':'inherit'}})
        page.categories = load_rule_categories(page.config_path, page.db_path)
        page._populate_list()
        page._load_category('coding')
        page.edit_processes.setPlainText('WindowsTerminal.exe')
        draft = page._draft_categories()['coding']['match']
        assert draft['process_names_mode'] == 'replace'
        assert draft['title_keywords_mode'] == 'inherit'
        assert page._test_draft('Code.exe')['category_key'] == 'other'
        page.edit_keywords.append('New study marker')
        assert page._draft_categories()['coding']['match']['title_keywords_mode'] == 'replace'
        preview = page._test_draft('chrome.exe','New study marker')
        assert preview['category_key'] == 'coding'
        assert page._save_current()
        runtime = Classifier(page.config_path,page.db_path)
        assert runtime.classify('Code.exe','')['category_key'] == 'other'
        assert runtime.classify('chrome.exe','New study marker') == preview
        assert 'Code.exe' not in page.edit_processes.toPlainText()
        assert database.load_custom_rules(page.db_path)['coding']['title_patterns_mode'] == 'inherit'
    finally:
        page.close()


def test_reserved_hidden_name_rejected_before_persistence(tmp_path, monkeypatch):
    from desktop_activity_tracker import database
    from PySide6.QtWidgets import QMessageBox
    page = _build_page(tmp_path)
    warnings = []
    monkeypatch.setattr(QMessageBox, 'warning', lambda *args: warnings.append(args[-1]))
    try:
        _select_category(page, 'coding')
        before = database.load_custom_rules(page.db_path)
        page.edit_name.setText('挂机')
        assert page._save_current() is False
        assert database.load_custom_rules(page.db_path) == before
        assert page._dirty and 'coding' in page.categories
        assert warnings
    finally:
        page.close()
