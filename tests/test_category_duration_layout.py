import os

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import pytest
from PySide6.QtWidgets import QApplication
from daylens.gui.pages.category_stats import _CategoryCard


@pytest.mark.parametrize('hours', [120, 1200])
@pytest.mark.parametrize('updated', [False, True])
def test_long_category_duration_is_fully_visible(hours, updated):
    app = QApplication.instance() or QApplication([])
    seconds = hours * 3600 + 59 * 60
    card = _CategoryCard('work', '工作学习', 60 if updated else seconds, seconds, '#20BF6B')
    card.resize(900, 140)
    card.show()
    if updated:
        card.update_values(seconds, seconds)
    app.processEvents()
    label = card._time_lbl
    assert label.contentsRect().width() >= label.fontMetrics().horizontalAdvance(label.text())
    label.setStyleSheet('font-size: 24px;')
    app.processEvents()
    assert label.contentsRect().width() >= label.fontMetrics().horizontalAdvance(label.text())
    card.close()
