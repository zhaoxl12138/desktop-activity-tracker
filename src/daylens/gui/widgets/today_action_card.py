"""One compact homepage view for existing goal and task snapshots."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QBoxLayout, QFrame, QHBoxLayout, QLabel, QToolButton, QVBoxLayout,
)

from ...utils import fmt_seconds
from .. import style as ui_style
from .daily_goal_widgets import goal_summary
from .elided_label import ElidedLabel


class TodayActionCard(QFrame):
    goals_requested = Signal()
    tasks_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 10, 16, 10)
        outer.setSpacing(5)

        self.title = QLabel("今日行动")
        self.title.setStyleSheet(
            f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};"
        )
        outer.addWidget(self.title)

        self.sections_layout = QBoxLayout(QBoxLayout.LeftToRight)
        self.sections_layout.setContentsMargins(0, 0, 0, 0)
        self.sections_layout.setSpacing(12)
        goal_section, self.goal_status, self.goal_summary, self.goal_button = (
            self._section("今日计划", "查看目标 →")
        )
        task_section, self.task_status, self.task_summary, self.task_button = (
            self._section("任务洞察", "查看任务 →")
        )
        self.goal_button.clicked.connect(self.goals_requested)
        self.task_button.clicked.connect(self.tasks_requested)
        self.sections_layout.addWidget(goal_section, 1)
        self.divider = QFrame()
        self.divider.setFrameShape(QFrame.VLine)
        self.divider.setStyleSheet(f"color: {ui_style.COLORS['border']};")
        self.sections_layout.addWidget(self.divider)
        self.sections_layout.addWidget(task_section, 1)
        outer.addLayout(self.sections_layout)
        self.set_goal_model({"status": "no_goals", "goals": []})
        self.set_task_model({"status": "disabled", "tasks": []})

    @staticmethod
    def _section(heading: str, action: str):
        section = QFrame()
        layout = QVBoxLayout(section)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        top = QHBoxLayout()
        name = QLabel(heading)
        name.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {ui_style.COLORS['text']};"
        )
        status = QLabel()
        status.setTextFormat(Qt.PlainText)
        status.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
        top.addWidget(name)
        top.addStretch()
        top.addWidget(status)
        layout.addLayout(top)
        summary = ElidedLabel()
        summary.setTextFormat(Qt.PlainText)
        summary.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text']};")
        layout.addWidget(summary)
        button = QToolButton()
        button.setText(action)
        button.setAutoRaise(True)
        button.setCursor(Qt.PointingHandCursor)
        button.setStyleSheet(
            f"color: {ui_style.COLORS['primary']}; font-size: 12px;"
            "border: none; padding: 0; text-align: left;"
        )
        layout.addWidget(button, 0, Qt.AlignLeft)
        return section, status, summary, button

    def set_compact(self, compact: bool) -> None:
        self.sections_layout.setDirection(
            QBoxLayout.TopToBottom if compact else QBoxLayout.LeftToRight
        )
        self.divider.setFrameShape(QFrame.HLine if compact else QFrame.VLine)

    def set_goal_model(self, model: dict) -> None:
        goals = model.get("goals") or []
        unavailable = model.get("status") == "unavailable"
        self.goal_status.setText(
            "暂不可用" if unavailable else "已计划" if goals else "未设置"
        )
        if unavailable:
            self.goal_summary.setText("目标数据暂不可读")
            self.goal_summary.setPersistentToolTip(None)
        elif goals:
            goal = goals[0]
            summary = goal_summary(goal)
            self.goal_summary.setText(summary)
            self.goal_summary.setPersistentToolTip(summary)
        else:
            self.goal_summary.setText("尚未设置目标")
            self.goal_summary.setPersistentToolTip(None)

    def set_task_model(self, model: dict) -> None:
        status = model.get("status", "disabled")
        tasks = model.get("tasks") or []
        self.task_status.setText({
            "disabled": "未开启", "ready": "仅本地",
            "insufficient_data": "数据不足", "unavailable": "暂不可用",
        }.get(status, "待确认"))
        if status == "ready" and model.get("cloud_enabled"):
            self.task_status.setText("AI 已开启")
        if status == "disabled":
            summary = "在设置中心开启本地任务分析"
        elif status == "unavailable":
            summary = "任务证据暂不可读"
        elif not tasks:
            summary = "尚无可核对的任务候选"
        else:
            task = tasks[0]
            name = str(task.get("name") or "待确认任务")
            marker = "已确认" if task.get("status") == "confirmed" else "待确认"
            summary = f"{name} · {fmt_seconds(int(task.get('engaged_seconds') or 0))} · {marker}"
        self.task_summary.setText(summary)
        self.task_summary.setPersistentToolTip(
            summary if tasks and status not in ("disabled", "unavailable") else None
        )
