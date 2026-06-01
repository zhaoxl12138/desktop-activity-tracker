"""Today overview page - summary cards, efficiency score, and suggestions."""

from datetime import datetime

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ... import database
from ...exporter import _calculate_efficiency_score, _generate_suggestions
from ...utils import fmt_seconds
from ..style import COLORS


class TodayOverviewPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self.cards = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        layout.setSpacing(18)

        self.hero_card = self._build_hero_card()
        layout.addWidget(self.hero_card)

        stats_grid = QGridLayout()
        stats_grid.setHorizontalSpacing(14)
        stats_grid.setVerticalSpacing(14)

        stats_grid.addWidget(
            self._make_stat_card("work", "学习 / 工作", "专注投入", COLORS["coding_green"]), 0, 0
        )
        stats_grid.addWidget(
            self._make_stat_card("social", "社交通讯", "聊天与沟通", COLORS["social_teal"]), 0, 1
        )
        stats_grid.addWidget(
            self._make_stat_card("entertainment", "视频娱乐", "被动消费", COLORS["video_orange"]), 1, 0
        )
        stats_grid.addWidget(
            self._make_stat_card("idle", "挂机时间", "离开电脑 / 无操作", COLORS["idle_gray"]), 1, 1
        )
        layout.addLayout(stats_grid)

        bottom_grid = QGridLayout()
        bottom_grid.setHorizontalSpacing(14)
        bottom_grid.setVerticalSpacing(14)
        bottom_grid.addWidget(self._build_efficiency_panel(), 0, 0)
        bottom_grid.addWidget(self._build_suggestions_panel(), 0, 1)
        bottom_grid.setColumnStretch(0, 11)
        bottom_grid.setColumnStretch(1, 9)
        layout.addLayout(bottom_grid)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def _build_hero_card(self):
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['card_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 18px;
            }}
            """
        )
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        layout = QHBoxLayout(card)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(22)

        left = QVBoxLayout()
        left.setSpacing(6)

        date_label = QLabel(datetime.now().strftime("%Y-%m-%d"))
        date_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_muted']}; font-weight: 600;"
        )
        left.addWidget(date_label)

        title = QLabel("今日使用总览")
        title.setStyleSheet(f"font-size: 28px; font-weight: 800; color: {COLORS['text']};")
        left.addWidget(title)

        self.hero_summary = QLabel("正在读取今天的数据结构...")
        self.hero_summary.setWordWrap(True)
        self.hero_summary.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; line-height: 1.4;"
        )
        left.addWidget(self.hero_summary)
        left.addStretch()

        right = QVBoxLayout()
        right.setSpacing(12)
        right.setAlignment(Qt.AlignCenter)

        self.total_value = QLabel("--")
        self.total_value.setStyleSheet(
            f"font-size: 44px; font-weight: 800; color: {COLORS['text']};"
        )
        right.addWidget(self.total_value, 0, Qt.AlignRight)

        self.focus_badge = QLabel("学习占比 --")
        self.focus_badge.setStyleSheet(
            f"""
            font-size: 12px;
            font-weight: 700;
            color: {COLORS['primary']};
            background: {COLORS['panel_bg']};
            border: 1px solid {COLORS['border']};
            border-radius: 14px;
            padding: 6px 12px;
            """
        )
        right.addWidget(self.focus_badge, 0, Qt.AlignRight)

        layout.addLayout(left, 3)
        layout.addLayout(right, 2)
        return card

    def _make_stat_card(self, key, title, subtitle, accent_color):
        card = QFrame()
        card.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['card_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 16px;
            }}
            """
        )

        layout = QVBoxLayout(card)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet(
            f"font-size: 15px; font-weight: 700; color: {COLORS['text']};"
        )
        layout.addWidget(title_label)

        value_label = QLabel("--")
        value_label.setStyleSheet(
            f"font-size: 34px; font-weight: 800; color: {accent_color};"
        )
        layout.addWidget(value_label)

        subtitle_label = QLabel(subtitle)
        subtitle_label.setStyleSheet(
            f"font-size: 12px; color: {COLORS['text_secondary']};"
        )
        layout.addWidget(subtitle_label)

        ratio_label = QLabel("占活跃时间 --")
        ratio_label.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        layout.addWidget(ratio_label)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(False)
        progress.setFixedHeight(8)
        progress.setStyleSheet(
            f"""
            QProgressBar {{
                background: {COLORS['panel_bg']};
                border: none;
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {accent_color};
                border-radius: 4px;
            }}
            """
        )
        layout.addWidget(progress)

        self.cards[key] = {
            "value_label": value_label,
            "ratio_label": ratio_label,
            "progress": progress,
        }
        return card

    def _build_efficiency_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['card_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 18px;
            }}
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(14)

        title = QLabel("效率评分")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)

        score_row = QHBoxLayout()
        score_row.setSpacing(18)

        score_wrap = QFrame()
        score_wrap.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 20px;
            }}
            """
        )
        score_wrap_layout = QVBoxLayout(score_wrap)
        score_wrap_layout.setContentsMargins(22, 18, 22, 18)
        score_wrap_layout.setSpacing(2)

        self.eff_score = QLabel("--")
        self.eff_score.setStyleSheet(
            f"font-size: 46px; font-weight: 800; color: {COLORS['primary']};"
        )
        score_wrap_layout.addWidget(self.eff_score, 0, Qt.AlignCenter)

        score_hint = QLabel("分 / 100")
        score_hint.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        score_wrap_layout.addWidget(score_hint, 0, Qt.AlignCenter)
        score_row.addWidget(score_wrap, 0)

        meta_wrap = QVBoxLayout()
        meta_wrap.setSpacing(10)

        self.eff_grade = QLabel("等待数据")
        self.eff_grade.setStyleSheet(
            f"""
            font-size: 14px;
            font-weight: 700;
            color: {COLORS['text']};
            background: {COLORS['panel_bg']};
            border: 1px solid {COLORS['border']};
            border-radius: 14px;
            padding: 7px 12px;
            """
        )
        meta_wrap.addWidget(self.eff_grade, 0, Qt.AlignLeft)

        self.eff_detail = QLabel("暂无分析")
        self.eff_detail.setWordWrap(True)
        self.eff_detail.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; line-height: 1.4;"
        )
        meta_wrap.addWidget(self.eff_detail)

        self.work_ratio = QLabel("学习/工作占比 --")
        self.work_ratio.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        meta_wrap.addWidget(self.work_ratio)

        self.ent_ratio = QLabel("娱乐占比 --")
        self.ent_ratio.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        meta_wrap.addWidget(self.ent_ratio)

        meta_wrap.addStretch()
        score_row.addLayout(meta_wrap, 1)
        layout.addLayout(score_row)
        return panel

    def _build_suggestions_panel(self):
        panel = QFrame()
        panel.setStyleSheet(
            f"""
            QFrame {{
                background: {COLORS['card_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 18px;
            }}
            """
        )

        layout = QVBoxLayout(panel)
        layout.setContentsMargins(24, 22, 24, 22)
        layout.setSpacing(12)

        title = QLabel("提醒与建议")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        layout.addWidget(title)

        self.suggestion_title = QLabel("先看今天最突出的模式")
        self.suggestion_title.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']};"
        )
        layout.addWidget(self.suggestion_title)

        self.suggestion_text = QTextEdit()
        self.suggestion_text.setReadOnly(True)
        self.suggestion_text.setStyleSheet(
            f"""
            QTextEdit {{
                font-size: 13px;
                color: {COLORS['text_secondary']};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 14px;
                padding: 12px;
            }}
            """
        )
        layout.addWidget(self.suggestion_text, 1)
        return panel

    def refresh(self):
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            totals = stats.get("totals", {})
            effective = totals.get("effective_seconds", 0) or 0
            idle_sec = totals.get("idle_seconds", 0) or 0
            total_sec = effective + idle_sec

            work_cats = {"ai_tools", "coding", "reading", "creative"}
            work_sec = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") in work_cats
            )
            social_sec = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") == "social"
            )
            video_sec = sum(
                item.get("effective_seconds", 0) or 0
                for item in stats.get("by_category", [])
                if item.get("category_key") in ("video", "gaming")
            )

            self.total_value.setText(fmt_seconds(total_sec))

            work_ratio = int(round((work_sec / effective) * 100)) if effective else 0
            ent_ratio = int(round((video_sec / effective) * 100)) if effective else 0

            self.hero_summary.setText(
                f"今天总共记录 {fmt_seconds(total_sec)}，其中活跃使用 {fmt_seconds(effective)}。"
                f" 当前最主要的结构是学习/工作 {fmt_seconds(work_sec)}，娱乐 {fmt_seconds(video_sec)}。"
            )
            self.focus_badge.setText(f"学习占比 {work_ratio}%")

            self._update_card("work", work_sec, effective)
            self._update_card("social", social_sec, effective)
            self._update_card("entertainment", video_sec, effective)
            self._update_card("idle", idle_sec, total_sec)

            score = _calculate_efficiency_score(work_sec, video_sec, effective)
            self._update_efficiency(score, work_ratio, ent_ratio)

            suggestions, _, _ = _generate_suggestions(self.db_path, today, stats)
            if suggestions:
                self.suggestion_title.setText("系统基于今天的数据给出的提醒")
                self.suggestion_text.setText("\n".join(f"• {item}" for item in suggestions))
            else:
                self.suggestion_title.setText("今天暂时没有触发额外提醒")
                self.suggestion_text.setText("目前没有明显异常，继续保持记录即可。")
        except Exception:
            import traceback

            traceback.print_exc()

    def _update_card(self, key, seconds_value, base_seconds):
        ratio = int(round((seconds_value / base_seconds) * 100)) if base_seconds else 0
        self.cards[key]["value_label"].setText(fmt_seconds(seconds_value))
        self.cards[key]["ratio_label"].setText(f"占比 {ratio}%")
        self.cards[key]["progress"].setValue(max(0, min(100, ratio)))

    def _update_efficiency(self, score, work_ratio, ent_ratio):
        self.work_ratio.setText(f"学习/工作占比 {work_ratio}%")
        self.ent_ratio.setText(f"娱乐占比 {ent_ratio}%")

        if score is None:
            self.eff_score.setText("--")
            self.eff_grade.setText("数据不足")
            self.eff_grade.setStyleSheet(
                f"""
                font-size: 14px;
                font-weight: 700;
                color: {COLORS['text_muted']};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 14px;
                padding: 7px 12px;
                """
            )
            self.eff_detail.setText("活跃数据还不够，暂时不做评分。")
            return

        self.eff_score.setText(str(score))
        if score >= 80:
            grade = "优秀"
            accent = COLORS["coding_green"]
            detail = "今天明显是高专注结构，学习/工作占据主导。"
        elif score >= 60:
            grade = "良好"
            accent = COLORS["primary"]
            detail = "整体结构健康，主任务与其他活动比例比较平衡。"
        elif score >= 40:
            grade = "一般"
            accent = COLORS["warning_yellow"]
            detail = "有效时间存在，但专注占比不高，容易被其他内容稀释。"
        else:
            grade = "需改进"
            accent = COLORS["danger_red"]
            detail = "娱乐或杂项占比偏高，主任务投入明显不足。"

        self.eff_grade.setText(grade)
        self.eff_grade.setStyleSheet(
            f"""
            font-size: 14px;
            font-weight: 700;
            color: white;
            background: {accent};
            border: none;
            border-radius: 14px;
            padding: 7px 12px;
            """
        )
        self.eff_detail.setText(detail)
