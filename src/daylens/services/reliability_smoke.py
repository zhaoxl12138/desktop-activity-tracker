"""Packaged correction smoke using synthetic state, never the user's database."""
from pathlib import Path
from tempfile import TemporaryDirectory


def run_correction_smoke(app):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QDialogButtonBox, QWidget
    from ..gui.pages.live_monitor import LiveMonitorPage
    from .classification_state_service import state_revision
    from .intelligence_evidence import load_patterns, update_pattern_category
    from .intelligence_state import load_overrides
    original = LiveMonitorPage.__dict__['_review_directory']
    with TemporaryDirectory() as directory:
        LiveMonitorPage._review_directory = staticmethod(lambda: Path(directory))
        page = None
        management = None
        try:
            page = LiveMonitorPage()
            for title in ('学习中心 视频课程 公共知识', 'Another page'):
                page.on_sample_updated({'process_name':'chrome.exe','window_title':title,
                                        'category_key':'browser_general'})
            page.table.selectRow(1)
            page.on_sample_updated({'process_name':'chrome.exe','window_title':'Newest page',
                                    'category_key':'browser_general'})
            chosen = []
            def choose():
                dialog = app.activeModalWidget()
                if dialog is not None and hasattr(dialog, 'category_combo'):
                    chosen.append(dialog.title_label.text())
                    dialog.category_combo.setCurrentIndex(dialog.category_combo.findData('reading'))
                    dialog.buttons.button(QDialogButtonBox.Save).click()
            QTimer.singleShot(0, choose)
            page._correct_current()
            if chosen != ['学习中心 视频课程 公共知识'] or not load_overrides(directory):
                return False
            pattern = load_patterns(directory)[0]
            if not update_pattern_category(directory, pattern['id'], 'video'):
                return False
            page.on_classification_applied(state_revision(directory))
            if load_patterns(directory)[0]['category'] != 'video':
                return False
            from ..gui.pages.classification_management import ClassificationManagementPage
            management = ClassificationManagementPage(page,QWidget())
            management.tabs.setCurrentIndex(1)
            management.table.selectRow(0)
            def edit():
                dialog = app.activeModalWidget()
                if dialog is not None and hasattr(dialog,'category_combo'):
                    dialog.category_combo.setCurrentIndex(dialog.category_combo.findData('finance'))
                    dialog.buttons.button(QDialogButtonBox.Save).click()
            QTimer.singleShot(0,edit)
            management._edit()
            if next(iter(load_overrides(directory).values()))['category'] != 'finance':
                return False
            management._toggle()
            if next(iter(load_overrides(directory).values())).get('enabled',True):
                return False
            management._undo()
            return next(iter(load_overrides(directory).values())).get('enabled',True)
        finally:
            if management is not None:
                management.close()
                management.deleteLater()
            if page is not None:
                page.close()
                page.deleteLater()
                app.processEvents()
            LiveMonitorPage._review_directory = original
