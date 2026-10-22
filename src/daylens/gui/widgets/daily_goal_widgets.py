"""Compact evidence-labelled summary of user-authored daily goals."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import style as ui_style
from ...utils import fmt_seconds


def goal_summary(goal: dict) -> str:
    if goal.get("type") == "outcome":
        state = "用户已确认" if goal.get("confirmed") else "等待用户确认"
        return f"{goal.get('title', '')} · {state}"
    target = fmt_seconds(int(goal.get("target_minutes") or 0) * 60)
    actual = goal.get("actual_seconds")
    if actual is None:
        reason = {"unconfirmed_task": "任务未确认",
                  "untrusted": "旧口径或异常记录，证据不足"}.get(
                      goal.get("evidence_status"), "证据不足")
        return f"{goal.get('title', '')} · 计划 {target} · {reason}"
    remaining = int(goal.get("difference_seconds") or 0)
    difference = (f"还差 {fmt_seconds(remaining)}" if remaining > 0
                  else "已达到计划时长")
    suffix = " · 部分证据不可比" if goal.get("evidence_status") == "untrusted" else ""
    return (f"{goal.get('title', '')} · 计划 {target} / 参与 {fmt_seconds(int(actual))}"
            f" · {difference}{suffix}")


class DailyGoalCard(QFrame):
    view_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        header = QHBoxLayout()
        title = QLabel("今日计划")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        self.status = QLabel("未设置")
        self.status.setTextFormat(Qt.PlainText)
        header.addWidget(self.status)
        outer.addLayout(header)
        self.goal_labels = []
        for _ in range(3):
            label = QLabel("")
            label.setTextFormat(Qt.PlainText)
            label.setWordWrap(True)
            label.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text']};")
            label.hide()
            outer.addWidget(label)
            self.goal_labels.append(label)
        self.empty = QLabel("今天尚未设置目标；投入时间不会被当成完成成果")
        self.empty.setTextFormat(Qt.PlainText)
        self.empty.setWordWrap(True)
        outer.addWidget(self.empty)
        button = QPushButton("管理目标")
        button.clicked.connect(self.view_requested)
        outer.addWidget(button)

    def set_model(self, model: dict) -> None:
        goals = model.get("goals") or []
        unavailable = model.get("status") == "unavailable"
        self.status.setText("暂不可用" if unavailable else "已计划" if goals else "未设置")
        self.empty.setVisible(not goals)
        self.empty.setText("目标数据暂不可读；原始记录不受影响" if unavailable
                           else "今天尚未设置目标；投入时间不会被当成完成成果")
        for index, label in enumerate(self.goal_labels):
            if index < len(goals):
                label.setText(goal_summary(goals[index]))
                label.setToolTip(str(goals[index].get("title") or ""))
                label.show()
            else:
                label.hide()
