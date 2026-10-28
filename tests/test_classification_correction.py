import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtCore import QTimer, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox


def test_dialog_real_save_and_cancel():
    from daylens.gui.widgets.classification_dialog import ClassificationDialog, CATEGORY_CHOICES
    from daylens.services.intelligence_client import LEGAL_CATEGORIES
    app = QApplication.instance() or QApplication([])
    assert {key for _, key in CATEGORY_CHOICES} == LEGAL_CATEGORIES
    dialog = ClassificationDialog(app_name='chrome.exe', title='<学习中心>', current_category='reading')
    assert dialog.selected_category() == 'reading'
    assert dialog.title_label.textFormat() == Qt.PlainText
    def save():
        dialog.category_combo.setCurrentIndex(dialog.category_combo.findData('video'))
        QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Save), Qt.LeftButton)
    QTimer.singleShot(0, save)
    assert dialog.exec() == QDialog.Accepted
    assert dialog.selected_category() == 'video'
    QTimer.singleShot(0, lambda: QTest.mouseClick(dialog.buttons.button(QDialogButtonBox.Cancel), Qt.LeftButton))
    assert dialog.exec() == QDialog.Rejected


def test_pattern_edit_preserves_metadata_and_exact_correction(tmp_path):
    from daylens.services.intelligence_evidence import load_patterns, update_pattern_category
    from daylens.services.intelligence_state import save_override, load_overrides
    save_override(tmp_path, 'chrome.exe', '学习中心 视频课程', 'reading')
    original = load_patterns(tmp_path)[0]
    assert update_pattern_category(tmp_path, original['id'], 'video')
    changed = load_patterns(tmp_path)[0]
    assert changed == dict(original, category='video')
    assert next(iter(load_overrides(tmp_path).values()))['category'] == 'video'
    with pytest.raises(ValueError):
        update_pattern_category(tmp_path, original['id'], 'invalid')
    assert not update_pattern_category(tmp_path, 'missing', 'reading')


def test_current_correction_saves_selected_sample(tmp_path, monkeypatch):
    from daylens.gui.pages import live_monitor as module
    from daylens.services.intelligence_state import load_overrides
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module.LiveMonitorPage, '_review_directory', staticmethod(lambda: tmp_path))
    page = module.LiveMonitorPage()
    page._correct_current()
    assert '暂无' in page.correction_status.text()
    page._samples = [{'process_name':'chrome.exe', 'window_title':'学习中心 视频课程', 'category_key':'browser_general'}]
    signals = []
    page.classification_corrected.connect(lambda: signals.append(True))
    def accept(self):
        self.category_combo.setCurrentIndex(self.category_combo.findData('reading'))
        return QDialog.Accepted
    monkeypatch.setattr(module.ClassificationDialog, 'exec', accept)
    page._correct_current()
    assert next(iter(load_overrides(tmp_path).values()))['category'] == 'reading'
    assert len(signals) == 1
    assert '已纠正' in page.correction_status.text()


def test_manage_pattern_real_dialog_flow(tmp_path, monkeypatch):
    from daylens.gui.pages import live_monitor as module
    from daylens.services.intelligence_evidence import save_pattern, load_patterns
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module.LiveMonitorPage, '_review_directory', staticmethod(lambda: tmp_path))
    original = save_pattern(tmp_path, 'chrome.exe', '学习中心 视频课程', 'reading')
    page = module.LiveMonitorPage()
    signals = []
    page.classification_corrected.connect(lambda: signals.append(True))
    stages = []
    timer = QTimer()
    def drive():
        modal = app.activeModalWidget()
        if not isinstance(modal, module.ChoiceDialog):
            return
        if modal.windowTitle() == '纠正分类':
            modal.category_combo.setCurrentIndex(modal.category_combo.findData('video'))
        stages.append(modal.windowTitle())
        QTest.mouseClick(modal.buttons.button(QDialogButtonBox.Save), Qt.LeftButton)
    timer.timeout.connect(drive)
    timer.start(20)
    QTimer.singleShot(3000, lambda: app.activeModalWidget() and app.activeModalWidget().reject())
    page._manage_patterns()
    timer.stop()
    assert stages == ['管理已确认模式', '模式操作', '纠正分类']
    assert load_patterns(tmp_path)[0] == dict(original, category='video')
    assert len(signals) == 1


def test_cancel_correction_writes_nothing(tmp_path, monkeypatch):
    from daylens.gui.pages import live_monitor as module
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(module.LiveMonitorPage, '_review_directory', staticmethod(lambda: tmp_path))
    page = module.LiveMonitorPage()
    page._samples = [{'process_name':'chrome.exe', 'window_title':'学习中心', 'category_key':'reading'}]
    monkeypatch.setattr(module.ClassificationDialog, 'exec', lambda self: QDialog.Rejected)
    page._correct_current()
    assert not (tmp_path / 'manual_decisions.json').exists()


def test_immediate_correction_reports_history_and_local_rule(tmp_path, monkeypatch):
    from daylens.app_paths import AppPaths
    from daylens.gui.pages import live_monitor as module
    from daylens.services import classification_correction_service as service
    from daylens.services.classification_correction_service import CorrectionResult

    app = QApplication.instance() or QApplication([])
    paths = AppPaths.from_database(tmp_path / "usage.db", program_dir=tmp_path)
    page = module.LiveMonitorPage(paths=paths)
    page._samples = [{
        "process_name": "Probably Stolen.exe",
        "window_title": "Probably Stolen",
        "normalized_title": "Probably Stolen",
        "category_key": "other",
    }]

    monkeypatch.setattr(
        module.ClassificationDialog,
        "exec",
        lambda self: (
            self.category_combo.setCurrentIndex(self.category_combo.findData("gaming"))
            or QDialog.Accepted
        ),
    )
    captured = {}

    def apply(**kwargs):
        captured.update(kwargs)
        return CorrectionResult(6, True, False, True, str(tmp_path / "audit.json"))

    monkeypatch.setattr(service, "apply_classification_correction", apply)
    emitted = []
    page.classification_history_changed.connect(emitted.append)
    page._correct_current()

    assert captured["db_path"] == str(paths.database)
    assert captured["normalized_title"] == "Probably Stolen"
    assert captured["category_key"] == "gaming"
    assert "已修正今天6条记录，并加入本地规则" in page.correction_status.text()
    assert emitted == [{
        "updated_sessions": 6,
        "rule_changed": True,
        "shared_browser": False,
    }]


def test_browser_correction_reports_title_rule_without_process_rule(tmp_path, monkeypatch):
    from daylens.app_paths import AppPaths
    from daylens.gui.pages import live_monitor as module
    from daylens.services import classification_correction_service as service
    from daylens.services.classification_correction_service import CorrectionResult

    app = QApplication.instance() or QApplication([])
    paths = AppPaths.from_database(tmp_path / "usage.db", program_dir=tmp_path)
    page = module.LiveMonitorPage(paths=paths)
    page._samples = [{
        "process_name": "chrome.exe",
        "window_title": "Movie - Google Chrome",
        "normalized_title": "Movie",
        "category_key": "other",
    }]
    monkeypatch.setattr(module.ClassificationDialog, "exec", lambda self: QDialog.Accepted)
    monkeypatch.setattr(
        service,
        "apply_classification_correction",
        lambda **_kwargs: CorrectionResult(2, False, True, True, str(tmp_path / "audit.json")),
    )

    page._correct_current()
    assert "已修正今天2条记录，并保存标题规则" in page.correction_status.text()
