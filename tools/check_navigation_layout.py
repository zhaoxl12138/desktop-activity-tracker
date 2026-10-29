"""Isolated shell captures for statistics navigation and the combined status."""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from tests.test_stage_c_shell import _window
from tools.check_history_cards_layout import sample


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei', 10))
    output = ROOT/'tmp'/'navigation-layout'/os.environ.get('QT_SCALE_FACTOR','1')
    output.mkdir(parents=True, exist_ok=True)
    scale = float(os.environ.get('QT_SCALE_FACTOR', '1'))
    with tempfile.TemporaryDirectory() as directory, patch('daylens.get_data_dir', return_value=directory), patch('desktop_activity_tracker.get_data_dir', return_value=directory):
        _app, window = _window()
        work, entertainment = sample()
        window.pages['today'].rhythm_card.set_data(work)
        window.pages['today'].entertainment_history_card.set_data(entertainment)
        window.pages['today'].rhythm_card.set_mode('7d')
        window.capsule_values['total'].setText('4时3分')
        for theme in ('dark','light'):
            if window.current_theme != theme:
                window._toggle_theme(theme == 'dark')
            for width,height in ((1280,720),(1920,1080)):
                logical_width = int(width / scale)
                logical_height = int(height / scale)
                window.resize(logical_width, logical_height)
                for page in ('today','live','settings'):
                    window.navigate_to(page)
                    app.processEvents()
                    app.processEvents()
                    assert window.nav_list.count() == 5
                    assert window.nav_list.item(1).data(Qt.UserRole)['title'] == '数据统计'
                    assert window.nav_list.item(4).data(Qt.UserRole)['key'] == 'settings'
                    assert window.btn_pause.height() == 44
                    assert window.top_record_status.isVisible()
                    assert window.top_record_status.parentWidget() is window._summary_capsule
                    capsule_end = window._summary_capsule.mapTo(window._top_bar,QPoint(window._summary_capsule.width(),0)).x()
                    button_start = window.btn_pause.mapTo(window._top_bar,QPoint(0,0)).x()
                    assert capsule_end < button_start
                    if page == 'live':
                        assert window.pages['stats'].tabs.currentWidget() is window.pages['live']
                    assert window.width() <= logical_width
                    assert window.height() <= logical_height
                    assert window.grab().save(str(output/f'{theme}-{width}x{height}-{page}.png'))
        window.close()
    print(f'Navigation/status captures passed: {output}')


if __name__ == '__main__':
    main()
