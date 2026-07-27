from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from daylens.gui.widgets.elided_label import ElidedLabel


def test_elided_label_uses_font_width_and_preserves_full_tooltip():
    app = QApplication.instance() or QApplication([])
    full_text = "这是一个会根据实际字体宽度省略的很长应用名称"
    label = ElidedLabel(full_text)
    label.resize(80, 24)
    label.show()
    app.processEvents()

    assert label.text() != full_text
    assert "…" in label.text()
    assert label.toolTip() == full_text

    label.resize(1_000, 24)
    app.processEvents()

    assert label.text() == full_text
    assert label.toolTip() == ""
    label.deleteLater()


def test_multiline_elided_label_limits_each_poetry_line_independently():
    app = QApplication.instance() or QApplication([])
    full_text = (
        "第一行诗句非常非常长需要在当前宽度内显示\n"
        "第二行诗句也非常非常长并且保留作者信息"
    )
    label = ElidedLabel(full_text, max_lines=2)
    label.resize(100, 48)
    label.show()
    app.processEvents()

    visible_lines = label.text().splitlines()
    assert len(visible_lines) == 2
    assert all("…" in line for line in visible_lines)
    assert label.toolTip() == full_text
    label.deleteLater()
