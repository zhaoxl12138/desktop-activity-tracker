from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from daylens.gui.pages.category_stats import _CategoryCard
from daylens.gui.pages.category_stats import CategoryStatsPage
from daylens.gui.pages import category_stats
from daylens.gui.widgets.elided_label import ElidedLabel


def test_existing_category_card_updates_renamed_label_and_preserves_tooltip():
    app = QApplication.instance() or QApplication([])
    card = _CategoryCard(
        "custom",
        "旧分类名称",
        60,
        120,
        "#3b82f6",
    )
    renamed = "这是一个很长的用户自定义分类名称"

    card.update_values(90, 180, renamed)
    card.show()
    app.processEvents()

    assert isinstance(card._name_lbl, ElidedLabel)
    assert card._name_lbl.fullText() == renamed
    assert card._name_lbl.toolTip() == renamed
    card.deleteLater()


def test_category_page_removes_empty_placeholder_when_data_arrives(
    tmp_path,
    monkeypatch,
):
    app = QApplication.instance() or QApplication([])
    summaries = iter(
        [
            {
                "today": "2026-07-26",
                "categories": [],
                "total_effective_seconds": 0,
                "total_label": "暂无数据",
            },
            {
                "today": "2026-07-26",
                "categories": [
                    {
                        "category_key": "work",
                        "category_name": "工作学习",
                        "effective_seconds": 120,
                    }
                ],
                "total_effective_seconds": 120,
                "total_label": "共 2 分钟",
            },
        ]
    )
    monkeypatch.setattr(
        category_stats.category_stats_service,
        "load_category_summary",
        lambda _db_path: next(summaries),
    )
    page = CategoryStatsPage(str(tmp_path / "usage.db"))
    page._is_active = True

    page.refresh()
    assert page._empty_label is not None
    assert page._empty_label.isHidden() is False

    page.refresh()

    assert page._empty_label is None
    assert set(page._cards) == {"work"}
    page.deleteLater()
    app.processEvents()
