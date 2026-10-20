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
