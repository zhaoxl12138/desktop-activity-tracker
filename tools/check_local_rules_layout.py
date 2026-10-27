"""Isolated local-rule panels and optional-title dialogs with synthetic rules."""
import os
import sys
import tempfile
from pathlib import Path
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'src')]
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea
from tests.test_rule_config_page import _build_page, _select_category
from desktop_activity_tracker.gui import style
from desktop_activity_tracker.gui.widgets.rule_application_dialog import RuleApplicationDialog


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/seguiemj.ttf')
    app.setFont(QFont('Microsoft YaHei',10))
    scale = float(os.environ.get('QT_SCALE_FACTOR','1'))
    output = ROOT/'tmp'/'local-rules-layout'/str(scale)
    output.mkdir(parents=True,exist_ok=True)
    for theme in ('dark','light'):
        style.apply_theme(theme)
        for width,height in ((1280,720),(1920,1080)):
            with tempfile.TemporaryDirectory() as directory:
                page = _build_page(Path(directory))
                _select_category(page,'coding')
                scroll = QScrollArea()
                scroll.setStyleSheet(style.get_global_style()+style.get_input_style())
                scroll.setWidgetResizable(True)
                scroll.setWidget(page)
                scroll.resize(min(1400,int(width/scale*.92)),min(850,int(height/scale*.88)))
                scroll.show()
                for expanded in (False,True):
                    page.advanced_toggle.setChecked(expanded)
                    app.processEvents()
                    app.processEvents()
                    assert page.edit_keywords.isVisible() == expanded
                    assert page.edit_rule.isVisible() == expanded
                    assert not page._dirty
                    assert page.width() <= scroll.viewport().width(), (theme,width,scale,page.width(),scroll.viewport().width())
                    assert not page.match_card.geometry().intersects(page.action_bar.geometry())
                    if expanded:
                        assert not page.match_card.geometry().intersects(page.advanced_panel.geometry())
                    for button in (page.btn_add_app,page.btn_remove_app,page.btn_more,page.btn_debug,page.btn_save):
                        assert button.width() >= button.fontMetrics().horizontalAdvance(button.text())+12
                    assert scroll.grab().save(str(output/f'{theme}-{width}x{height}-{"advanced" if expanded else "simple"}.png'))
                scroll.close()
            for testing in (False,True):
                dialog = RuleApplicationDialog(['Code.exe','chrome.exe','很长的示例应用名称.exe'], testing=testing)
                dialog.resize(440,dialog.sizeHint().height())
                dialog.show()
                app.processEvents()
                assert dialog.width() <= width/scale
                assert dialog.height() <= height/scale
                assert dialog.title.isVisible() == testing
                assert dialog.grab().save(str(output/f'{theme}-{width}x{height}-{"test" if testing else "add"}.png'))
                dialog.close()
    print(f'Local rule layout captures passed: {output}')


if __name__ == '__main__':
    main()
