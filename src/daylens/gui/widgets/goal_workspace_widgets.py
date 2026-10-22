"""Presentation-only widgets for the daily goal workspace."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QMenu, QProgressBar, QPushButton,
    QToolButton, QVBoxLayout,
)

from ...utils import fmt_seconds
from .. import style as ui_style
from .elided_label import ElidedLabel


class GoalEmptyState(QFrame):
    add_time_requested = Signal()
    add_outcome_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("goalEmptyState")
        self.setMaximumHeight(300)
        self.setStyleSheet(
            f"QFrame#goalEmptyState {{ background: {ui_style.COLORS['card_bg_alt']}; "
            f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(10)
        layout.setAlignment(Qt.AlignCenter)
        icon = QLabel("◎")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet(f"font-size: 30px; color: {ui_style.COLORS['primary']};")
        layout.addWidget(icon)
        self.title = QLabel("今天还没有设置目标")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {ui_style.COLORS['text']};")
        layout.addWidget(self.title)
        hint = QLabel("最多 3 项，先从一项开始")
        hint.setAlignment(Qt.AlignCenter)
        hint.setStyleSheet(f"color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(hint)
        actions = QHBoxLayout()
        actions.setAlignment(Qt.AlignCenter)
        self.time_button = QPushButton("＋ 时间目标")
        self.outcome_button = QPushButton("＋ 成果目标")
        self.time_button.clicked.connect(self.add_time_requested)
        self.outcome_button.clicked.connect(self.add_outcome_requested)
        self.time_button.setStyleSheet(ui_style.get_button_primary_style())
        self.outcome_button.setStyleSheet(ui_style.get_button_secondary_style())
        actions.addWidget(self.time_button)
        actions.addWidget(self.outcome_button)
        layout.addLayout(actions)
        example = QLabel("例如：学习 90 分钟 · 完成一篇笔记")
        example.setAlignment(Qt.AlignCenter)
        example.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        layout.addWidget(example)


class GoalTile(QFrame):
    edit_requested = Signal(str)
    delete_requested = Signal(str)
    confirm_requested = Signal(str)

    def __init__(self, goal: dict, parent=None):
        super().__init__(parent)
        self.goal_id = str(goal["id"])
        self.setObjectName("goalTile")
        self.setMinimumWidth(0)
        self.setMaximumWidth(720)
        self.setStyleSheet(
            f"QFrame#goalTile {{ background: {ui_style.COLORS['card_bg_alt']}; "
            f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 12px; }}"
        )
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(9)
        header = QHBoxLayout()
        self.title = ElidedLabel(str(goal.get("title") or ""))
        self.title.setTextFormat(Qt.PlainText)
        self.title.setStyleSheet(f"font-size: 16px; font-weight: 700; color: {ui_style.COLORS['text']};")
        self.title.setPersistentToolTip(self.title.fullText())
        header.addWidget(self.title, 1)
        self.menu_button = QToolButton()
        self.menu_button.setText("···")
        self.menu_button.setToolTip("目标操作")
        self.menu_button.setAccessibleName(f"{self.title.fullText()}的操作")
        self.menu_button.setStyleSheet(
            f"QToolButton {{ background: {ui_style.COLORS['panel_bg_alt']}; "
            f"color: {ui_style.COLORS['text']}; border: 1px solid {ui_style.COLORS['border']}; "
            "border-radius: 6px; padding: 3px 10px; }"
        )
        menu = QMenu(self.menu_button)
        menu.setStyleSheet(
            f"QMenu {{ background: {ui_style.COLORS['panel_bg_alt']}; "
            f"color: {ui_style.COLORS['text']}; border: 1px solid {ui_style.COLORS['border']}; }}"
            f"QMenu::item:selected {{ background: {ui_style.COLORS['primary']}; }}"
        )
        menu.addAction("编辑目标", lambda: self.edit_requested.emit(self.goal_id))
        menu.addAction("删除目标", lambda: self.delete_requested.emit(self.goal_id))
        self.menu_button.setMenu(menu)
        self.menu_button.setPopupMode(QToolButton.InstantPopup)
        header.addWidget(self.menu_button)
        layout.addLayout(header)
        self.kind = QLabel()
        self.kind.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.kind)
        self.state = QLabel()
        self.state.setTextFormat(Qt.PlainText)
        self.state.setStyleSheet(f"font-size: 14px; font-weight: 600; color: {ui_style.COLORS['text']};")
        layout.addWidget(self.state)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {ui_style.COLORS['panel_bg']}; border: 0; border-radius: 4px; }} "
            f"QProgressBar::chunk {{ background: {ui_style.COLORS['primary']}; border-radius: 4px; }}"
        )
        layout.addWidget(self.progress)
        self.evidence = QLabel()
        self.evidence.setTextFormat(Qt.PlainText)
        self.evidence.setWordWrap(True)
        self.evidence.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.evidence)
        self.confirm_button = QPushButton()
        self.confirm_button.setStyleSheet(ui_style.get_button_secondary_style())
        self.confirm_button.clicked.connect(lambda: self.confirm_requested.emit(self.goal_id))
        layout.addWidget(self.confirm_button, 0, Qt.AlignLeft)
        self.set_goal(goal)

    def set_goal(self, goal: dict) -> None:
        """Refresh visible evidence without replacing the focused card widget."""
        self.goal_id = str(goal["id"])
        title = str(goal.get("title") or "")
        self.title.setText(title)
        self.title.setPersistentToolTip(title)
        self.menu_button.setAccessibleName(f"{title}的操作")
        is_outcome = goal.get("type") == "outcome"
        kind = "成果目标" if is_outcome else "时间目标"
        target = goal.get("target_id")
        from ...services.daily_goal_service import GOAL_CATEGORIES
        target = GOAL_CATEGORIES.get(target, {"coding": "编程", "office": "办公",
            "reading": "阅读学习", "creative": "创作", "ai_tools": "AI 工具"}.get(target, "任务"))
        self.kind.setText(kind + (f" · {target}" if target and not is_outcome else ""))
        self.progress.setVisible(not is_outcome)
        self.confirm_button.setVisible(is_outcome)
        if is_outcome:
            confirmed = bool(goal.get("confirmed"))
            self.state.setText("已确认" if confirmed else "待用户确认")
            self.evidence.setText("由你确认成果；投入时长不代表完成")
            self.confirm_button.setText("撤销确认" if confirmed else "确认成果")
        else:
            target_seconds = max(1, int(goal.get("target_minutes") or 0) * 60)
            actual = goal.get("actual_seconds")
            if actual is None:
                self.state.setText(f"计划 {fmt_seconds(target_seconds)} · 暂无可靠进度")
                self.progress.setValue(0)
                self.evidence.setText("统计依据不足，不能按 0% 计算")
            else:
                actual = max(0, int(actual))
                self.progress.setValue(min(100, round(actual * 100 / target_seconds)))
                percentage = actual * 100 / target_seconds
                display_percentage = f"{percentage:.1f}".rstrip("0").rstrip(".")
                self.state.setText(
                    f"已投入 {fmt_seconds(actual)} / 计划 {fmt_seconds(target_seconds)}"
                    f" · {display_percentage}%"
                )
                self.evidence.setText(
                    "已达计划时长" if actual >= target_seconds else
                    f"还差 {fmt_seconds(target_seconds - actual)}"
                )
