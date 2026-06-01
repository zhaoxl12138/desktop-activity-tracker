"""Today overview page - summary cards, efficiency score, suggestions."""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QTextEdit
)
from PySide6.QtCore import Qt, QTimer

from ... import database
from ...utils import fmt_seconds
from ...exporter import _calculate_efficiency_score, _generate_suggestions
from ..style import COLORS


class TodayOverviewPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        title = QLabel("今日概览")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(title)

        # 5 data cards — two rows
        cards_grid = QVBoxLayout()
        cards_grid.setSpacing(12)
        self.cards = {}

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        for key, label, color in [
            ("total", "总使用时长", COLORS["primary"]),
            ("work", "学习/工作", COLORS["coding_green"]),
            ("social", "社交通讯", "#1ABC9C"),
        ]:
            card = self._make_card(label, color)
            row1.addWidget(card)
            self.cards[key] = card
        cards_grid.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        for key, label, color in [
            ("entertainment", "视频娱乐", COLORS["video_orange"]),
            ("idle", "挂机时间", COLORS["idle_gray"]),
        ]:
            card = self._make_card(label, color)
            row2.addWidget(card)
            row2.addStretch()
            self.cards[key] = card
        cards_grid.addLayout(row2)

        layout.addLayout(cards_grid)

        # Efficiency score row
        eff_layout = QHBoxLayout()
        self.eff_score = QLabel("--")
        self.eff_score.setStyleSheet("font-size: 48px; font-weight: bold; color: #2C3E50;")
        self.eff_grade = QLabel("等待数据...")
        self.eff_grade.setStyleSheet("font-size: 14px; color: #7F8C8D; margin-left: 12px;")
        eff_layout.addWidget(self.eff_score)
        eff_layout.addWidget(self.eff_grade)
        eff_layout.addStretch()
        layout.addLayout(eff_layout)

        # Suggestions block
        self.suggestion_text = QTextEdit()
        self.suggestion_text.setReadOnly(True)
        self.suggestion_text.setMaximumHeight(100)
        self.suggestion_text.setStyleSheet("font-size: 13px; color: #2C3E50; background: #F5F6FA; border: none; padding: 8px;")
        layout.addWidget(self.suggestion_text)

        layout.addStretch()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def _make_card(self, label, color):
        card = QFrame()
        card.setObjectName("dataCard")
        card.setStyleSheet(f"""
            QFrame#dataCard {{
                background: #FFFFFF;
                border: 1px solid #E0E0E0;
                border-left: 4px solid {color};
                border-radius: 8px;
                padding: 16px;
            }}
        """)
        layout = QVBoxLayout(card)
        layout.setSpacing(6)
        value_label = QLabel("--")
        value_label.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {color};")
        title_label = QLabel(label)
        title_label.setStyleSheet("font-size: 12px; color: #7F8C8D;")
        layout.addWidget(value_label)
        layout.addWidget(title_label)
        card.value_label = value_label
        return card

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_sec = totals.get("idle_seconds", 0) or 0
            total_sec = effective + idle_sec

            work_cats = {"ai_tools", "coding", "reading", "creative"}
            work_sec = sum(c.get("effective_seconds", 0) or 0 for c in stats.get("by_category", []) if c["category_key"] in work_cats)
            social_sec = sum(c.get("effective_seconds", 0) or 0 for c in stats.get("by_category", []) if c["category_key"] == "social")
            video_sec = sum(c.get("effective_seconds", 0) or 0 for c in stats.get("by_category", []) if c["category_key"] in ("video", "gaming"))

            self.cards["total"].value_label.setText(fmt_seconds(total_sec))
            self.cards["work"].value_label.setText(fmt_seconds(work_sec))
            self.cards["social"].value_label.setText(fmt_seconds(social_sec))
            self.cards["entertainment"].value_label.setText(fmt_seconds(video_sec))
            self.cards["idle"].value_label.setText(fmt_seconds(idle_sec))

            score = _calculate_efficiency_score(work_sec, video_sec, effective)
            if score is not None:
                self.eff_score.setText(f"{score}")
                if score >= 80:
                    grade, color = "优秀", COLORS["coding_green"]
                elif score >= 60:
                    grade, color = "良好", COLORS["primary"]
                elif score >= 40:
                    grade, color = "一般", COLORS["warning_yellow"]
                else:
                    grade, color = "需改进", COLORS["danger_red"]
                self.eff_grade.setText(grade)
                self.eff_grade.setStyleSheet(f"font-size: 14px; color: {color}; margin-left: 12px;")
            else:
                self.eff_score.setText("--")
                self.eff_grade.setText("数据不足（<30分钟）")

            suggestions, _, _ = _generate_suggestions(self.db_path, today, stats)
            self.suggestion_text.setText("\n".join(f"• {s}" for s in suggestions) if suggestions else "暂无建议")
        except Exception as e:
            import sys, traceback
            print(f"[TodayOverview] refresh error: {e}", file=sys.stderr)
            traceback.print_exc()
