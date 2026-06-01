"""Today overview page - summary cards, efficiency score, suggestions."""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFrame, QLabel, QTextEdit
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont

from ... import database
from ...utils import fmt_seconds
from ...exporter import _calculate_efficiency_score, _generate_suggestions
from ..style import COLORS


CARD_VALUE_STYLE = "font-size: 26px; font-weight: 800;"
CARD_LABEL_STYLE = f"font-size: 12px; color: {COLORS['text_muted']};"


class TodayOverviewPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(18)

        # Card grid: row1 (3 cards) + row2 (2 cards, fill remaining space)
        self.cards = {}

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        for key, label, icon, color in [
            ("total", "总使用时长", "\U0001F552", COLORS["text"]),
            ("work", "学习/工作", "\U0001F4AA", COLORS["coding_green"]),
            ("social", "社交通讯", "\U0001F4AC", COLORS["social_teal"]),
        ]:
            card = self._make_card(icon, label, color)
            row1.addWidget(card, 1)
            self.cards[key] = card
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        for key, label, icon, color in [
            ("entertainment", "视频娱乐", "\U0001F3AE", COLORS["video_orange"]),
            ("idle", "挂机时间", "\U0001F4A4", COLORS["idle_gray"]),
        ]:
            card = self._make_card(icon, label, color)
            row2.addWidget(card, 1)
            self.cards[key] = card
        layout.addLayout(row2)

        # Efficiency score
        eff_frame = QFrame()
        eff_frame.setStyleSheet(
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 10px;"
        )
        eff_layout = QHBoxLayout(eff_frame)
        eff_layout.setContentsMargins(24, 18, 24, 18)
        eff_layout.setSpacing(16)

        eff_left = QVBoxLayout()
        eff_left.setSpacing(4)
        self.eff_score = QLabel("--")
        self.eff_score.setFont(QFont("Microsoft YaHei", 42, QFont.Bold))
        self.eff_score.setStyleSheet(f"color: {COLORS['primary']};")
        eff_label = QLabel("效率评分")
        eff_label.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; font-weight: 600;"
        )
        eff_left.addWidget(self.eff_score)
        eff_left.addWidget(eff_label)

        self.eff_grade = QLabel("等待数据...")
        self.eff_grade.setStyleSheet(
            "font-size: 15px; font-weight: 700; padding: 6px 18px;"
            "border-radius: 20px;"
        )
        eff_layout.addLayout(eff_left)
        eff_layout.addStretch()
        eff_layout.addWidget(self.eff_grade, 0, Qt.AlignVCenter)
        layout.addWidget(eff_frame)

        # Suggestions
        self.suggestion_text = QTextEdit()
        self.suggestion_text.setReadOnly(True)
        self.suggestion_text.setMaximumHeight(80)
        self.suggestion_text.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']};"
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 8px; padding: 12px;"
        )
        layout.addWidget(self.suggestion_text)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def _make_card(self, icon, label, accent_color):
        card = QFrame()
        card.setStyleSheet(
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 10px;"
        )
        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(4)
        icon_lbl = QLabel(icon)
        icon_lbl.setStyleSheet("font-size: 16px;")
        header.addWidget(icon_lbl)
        header.addStretch()
        layout.addLayout(header)

        value_label = QLabel("--")
        value_label.setStyleSheet(f"{CARD_VALUE_STYLE} color: {accent_color};")
        layout.addWidget(value_label)

        title_label = QLabel(label)
        title_label.setStyleSheet(CARD_LABEL_STYLE)
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
            work_sec = sum(c.get("effective_seconds", 0) or 0
                          for c in stats.get("by_category", [])
                          if c.get("category_key") in work_cats)
            social_sec = sum(c.get("effective_seconds", 0) or 0
                           for c in stats.get("by_category", [])
                           if c.get("category_key") == "social")
            video_sec = sum(c.get("effective_seconds", 0) or 0
                          for c in stats.get("by_category", [])
                          if c.get("category_key") in ("video", "gaming"))

            self.cards["total"].value_label.setText(fmt_seconds(total_sec))
            self.cards["work"].value_label.setText(fmt_seconds(work_sec))
            self.cards["social"].value_label.setText(fmt_seconds(social_sec))
            self.cards["entertainment"].value_label.setText(fmt_seconds(video_sec))
            self.cards["idle"].value_label.setText(fmt_seconds(idle_sec))

            score = _calculate_efficiency_score(work_sec, video_sec, effective)
            if score is not None:
                self.eff_score.setText(f"{score}")
                if score >= 80:
                    grade, bg = "优秀", COLORS["coding_green"]
                elif score >= 60:
                    grade, bg = "良好", COLORS["primary"]
                elif score >= 40:
                    grade, bg = "一般", COLORS["warning_yellow"]
                else:
                    grade, bg = "需改进", COLORS["danger_red"]
                self.eff_grade.setText(grade)
                self.eff_grade.setStyleSheet(
                    f"font-size: 15px; font-weight: 700; padding: 6px 18px;"
                    f"background: {bg}; color: white; border-radius: 20px;"
                )
            else:
                self.eff_score.setText("--")
                self.eff_grade.setText("数据不足")
                self.eff_grade.setStyleSheet(
                    f"font-size: 15px; font-weight: 700; padding: 6px 18px;"
                    f"background: {COLORS['border']}; color: {COLORS['text_muted']};"
                    f"border-radius: 20px;"
                )

            suggestions, _, _ = _generate_suggestions(self.db_path, today, stats)
            self.suggestion_text.setText(
                "\n".join(f"• {s}" for s in suggestions) if suggestions else ""
            )
            self.suggestion_text.setVisible(bool(suggestions))
        except Exception:
            import traceback
            traceback.print_exc()
