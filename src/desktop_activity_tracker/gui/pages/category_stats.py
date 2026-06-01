"""Category stats page - progress bar visualization per category."""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar, QScrollArea
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from ... import database
from ...utils import fmt_seconds
from ..style import COLORS, CATEGORY_COLOR_MAP


class CategoryStatsPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        self.error_lbl = QLabel()
        self.error_lbl.setStyleSheet(
            f"color: {COLORS['danger_red']}; font-size: 12px;"
            f"background: #3A1620; border: 1px solid {COLORS['danger_red']};"
            f"border-radius: 6px; padding: 10px;"
        )
        self.error_lbl.hide()
        layout.addWidget(self.error_lbl)

        # Scroll area for many categories
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(
            f"QScrollArea {{ border: none; background: transparent; }}"
        )

        self.cards_widget = QWidget()
        self.cards_widget.setStyleSheet("background: transparent;")
        self.cards_layout = QVBoxLayout(self.cards_widget)
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(8)
        self.cards_layout.addStretch()
        scroll.setWidget(self.cards_widget)
        layout.addWidget(scroll, 1)

        # Total summary bar
        self.total_label = QLabel()
        self.total_label.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; padding: 4px 0;"
        )
        layout.addWidget(self.total_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def refresh(self):
        # Remove existing cards (keep the stretch)
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.error_lbl.hide()

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            categories = stats.get("by_category", [])

            total_eff = sum(c.get("effective_seconds", 0) or 0 for c in categories)
            self.total_label.setText(
                f"今日有效总计：{fmt_seconds(total_eff)}  |  {len(categories)} 个分类"
            )

            if not categories:
                no_data = QLabel("暂无数据")
                no_data.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
                no_data.setAlignment(Qt.AlignCenter)
                self.cards_layout.insertWidget(0, no_data)
                self.cards_layout.addStretch()
                return

            for cat in categories:
                key = cat.get("category_key", "other")
                name = cat.get("category_name", "其他")
                secs = cat.get("effective_seconds", 0) or 0
                color = CATEGORY_COLOR_MAP.get(key, COLORS['idle_gray'])
                pct = int(secs / total_eff * 100) if total_eff > 0 else 0

                card = QFrame()
                card.setStyleSheet(
                    f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
                    f"border-radius: 12px;"
                )
                card_layout = QHBoxLayout(card)
                card_layout.setContentsMargins(16, 10, 16, 10)
                card_layout.setSpacing(12)

                # Color dot
                dot = QLabel()
                dot.setFixedSize(10, 10)
                dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
                card_layout.addWidget(dot)

                # Name
                name_lbl = QLabel(name)
                name_lbl.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
                name_lbl.setStyleSheet(f"color: {COLORS['text']};")
                name_lbl.setFixedWidth(90)
                card_layout.addWidget(name_lbl)

                # Progress bar — uses real percentage
                bar = QProgressBar()
                bar.setRange(0, 100)
                bar.setValue(pct)
                bar.setTextVisible(False)
                bar.setFixedHeight(16)
                bar.setStyleSheet(f"""
                    QProgressBar {{
                        background: {COLORS['panel_bg']};
                        border: none;
                        border-radius: 8px;
                    }}
                    QProgressBar::chunk {{
                        background: {color};
                        border-radius: 8px;
                    }}
                """)
                card_layout.addWidget(bar, 1)

                # Time
                time_lbl = QLabel(fmt_seconds(secs))
                time_lbl.setStyleSheet(
                    f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;"
                )
                time_lbl.setFixedWidth(80)
                time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                card_layout.addWidget(time_lbl)

                # Percentage
                pct_lbl = QLabel(f"{pct}%")
                pct_lbl.setStyleSheet(
                    f"font-size: 12px; color: {COLORS['text_muted']};"
                )
                pct_lbl.setFixedWidth(36)
                pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                card_layout.addWidget(pct_lbl)

                self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)

            # Re-add the bottom stretch
            self.cards_layout.addStretch()
        except Exception as e:
            import traceback
            self.error_lbl.setText(f"加载失败: {e}\n{traceback.format_exc()}")
            self.error_lbl.show()
