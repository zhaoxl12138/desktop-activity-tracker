from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QLabel, QWidget

from daylens.gui.wizard import _FlowLayout


def test_flow_layout_size_hints_do_not_recurse():
    app = QApplication.instance() or QApplication([])
    host = QWidget()
    layout = _FlowLayout(host)
    layout.addWidget(QLabel("one"))
    layout.addWidget(QLabel("two"))

    minimum = layout.minimumSize()
    hint = layout.sizeHint()

    assert minimum.width() >= 0
    assert minimum.height() >= 0
    assert hint.width() >= minimum.width()
    assert layout.heightForWidth(120) > 0
    host.deleteLater()
    app.processEvents()
