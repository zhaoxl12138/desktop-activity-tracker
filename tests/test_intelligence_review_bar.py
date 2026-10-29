from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QDialog

from daylens.gui.widgets import intelligence_review_bar as review_bar_module
from daylens.gui.widgets.intelligence_review_bar import IntelligenceReviewBar


def test_stale_result_is_bound_to_requested_period_after_user_switches(monkeypatch):
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(QDialog, "exec", lambda _self: 0)
    monkeypatch.setattr(review_bar_module, "render_review", lambda _result: "review")
    bar = IntelligenceReviewBar("unused.db")
    bar.period.setCurrentIndex(1)  # weekly is now visible
    bar.results.put((True, "daily", {"evidence_status": "stale"}))

    bar._poll()
    app.processEvents()

    assert "daily" in bar._stale_kinds
    assert bar.period.currentData() == "weekly"
    assert bar.button.text() == "生成 / 查看智能复盘"
    bar.period.setCurrentIndex(0)
    assert bar.button.text() == "重新分析旧数据"
    bar.deleteLater()
