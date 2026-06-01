"""Category stats page - progress bar visualization per category."""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame
)
from PySide6.QtCore import Qt, QTimer

from ... import database
from ...exporter import _fmt_seconds
from ..style import CATEGORY_COLOR_MAP


class CategoryStatsPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("分类统计")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        self.cards_layout = QVBoxLayout()
        self.cards_layout.setSpacing(10)
        layout.addLayout(self.cards_layout)

        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def refresh(self):
        # Clear existing cards
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            categories = stats.get("by_category", [])
            if not categories:
                no_data = QLabel("暂无数据")
                no_data.setStyleSheet("color: #7F8C8D; font-size: 14px;")
                self.cards_layout.addWidget(no_data)
                return

            max_sec = max(c.get("effective_seconds", 0) or 0 for c in categories) or 1

            for cat in categories:
                key = cat.get("category_key", "other")
                name = cat.get("category_name", "其他")
                secs = cat.get("effective_seconds", 0) or 0
                color = CATEGORY_COLOR_MAP.get(key, "#95A5A6")
                ratio = secs / max_sec if max_sec > 0 else 0

                card = QFrame()
                card.setStyleSheet("background: #FFFFFF; border: 1px solid #E0E0E0; border-radius: 6px; padding: 10px;")
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(12, 8, 12, 8)
                card_layout.setSpacing(12)

                name_lbl = QLabel(name)
                name_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #2C3E50;")
                name_lbl.setFixedWidth(100)
                card_layout.addWidget(name_lbl)

                bar_container = QFrame()
                bar_container.setStyleSheet("background: #F0F0F0; border-radius: 4px;")
                bar_container.setFixedHeight(20)
                bar = QFrame(bar_container)
                bar.setStyleSheet(f"background: {color}; border-radius: 4px;")
                bar.setFixedHeight(20)
                bar_width = max(10, int(ratio * 300))
                bar.setFixedWidth(bar_width)
                card_layout.addWidget(bar_container, 1)

                time_lbl = QLabel(_fmt_seconds(secs))
                time_lbl.setStyleSheet("font-size: 13px; color: #2C3E50;")
                time_lbl.setFixedWidth(100)
                time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                card_layout.addWidget(time_lbl)

                self.cards_layout.addWidget(card)
        except Exception:
            pass
