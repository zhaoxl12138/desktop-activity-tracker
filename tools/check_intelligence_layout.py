"""Offscreen full-window QA with isolated fixture data and no API calls."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'tests')]

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea
from test_gui_smoke import DummyWorker, _write_config
from daylens import database
from daylens.gui.main_window import MainWindow


def main():
    output = ROOT / 'tmp' / 'intelligence-layout'
    output.mkdir(parents=True, exist_ok=True)
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei', 10))
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / 'config.yaml'
        config = _write_config(config_path)
        db_path = root / 'usage.db'
        database.init_db(str(db_path)).close()
        reports = root / 'reports'
        reports.mkdir()
        with patch('daylens.gui.widgets.intelligence_settings.get_data_dir', return_value=directory), \
                patch('daylens.gui.widgets.intelligence_settings.credentials.read_key', return_value=None):
            window = MainWindow(str(root), config, str(db_path), str(config_path), str(reports), DummyWorker())
        window.show()
        window.resize(1280, 720)
        app.processEvents()
        assert window.size().width() == 1280 and window.size().height() == 720
        for page in ('settings', 'reports', 'live'):
            for i in range(window.nav_list.count()):
                if window.nav_list.item(i).data(Qt.UserRole)['key'] == page:
                    window.nav_list.setCurrentRow(i)
                    break
            app.processEvents()
            for scroll in window.findChildren(QScrollArea):
                if scroll.isVisible():
                    scroll.verticalScrollBar().setValue(0)
            app.processEvents()
            if page == 'settings':
                for _ in range(2):
                    for scroll in window.findChildren(QScrollArea):
                        if scroll.isVisible():
                            scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    app.processEvents()
                from daylens.gui.widgets.intelligence_settings import IntelligenceSettings
                card = window.findChild(IntelligenceSettings)
                card.grab().save(str(output / 'intelligence-settings-card.png'))
            widget = window.pages[page]
            assert widget.width() <= window.width()
            window.grab().save(str(output / f'{page}-1280x720.png'))
        assert MainWindow._suspend_dashboard_refresh(window)
        window.hide()
        window.deleteLater()
        app.processEvents()
        database.close_shared_read_conn()
    print(f'1280x720 captures and layout checks passed: {output}')


if __name__ == '__main__':
    main()
