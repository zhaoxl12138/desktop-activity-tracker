"""Compact Today card for optional, evidence-based task observations."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from .. import style as ui_style
from ...services.task_insights_service import task_review_label
from ...utils import fmt_seconds


class TaskInsightCard(QFrame):
    view_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("dashboardCard")
        self.setStyleSheet(ui_style.get_dashboard_card_style())
        self.setMinimumHeight(145)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 12, 16, 12)
        outer.setSpacing(5)
        header = QHBoxLayout()
        title = QLabel("任务洞察")
        title.setStyleSheet(f"font-size: 17px; font-weight: 800; color: {ui_style.COLORS['text']};")
        self.status = QLabel("未开启")
        self.status.setTextFormat(Qt.PlainText)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.status)
        outer.addLayout(header)
        self.task_labels = []
        for _ in range(3):
            label = QLabel("")
            label.setTextFormat(Qt.PlainText)
            label.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text']}; font-weight: 650;")
            label.hide()
            outer.addWidget(label)
            self.task_labels.append(label)
        self.observation = QLabel("在设置中心开启本地任务分析")
        self.observation.setTextFormat(Qt.PlainText)
        self.observation.setWordWrap(True)
        self.observation.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
        outer.addWidget(self.observation)
        self.view_button = QPushButton("查看任务链 · 纠正任务")
        self.view_button.clicked.connect(self.view_requested)
        outer.addWidget(self.view_button)

    def set_model(self, model: dict) -> None:
        status = model.get("status", "disabled")
        self.status.setText({
            "disabled": "未开启", "ready": "仅本地", "insufficient_data": "数据不足",
            "unavailable": "暂不可用",
        }.get(status, "等待确认"))
        if status == "ready" and model.get("cloud_enabled"):
            self.status.setText("AI 已开启")
        tasks = model.get("tasks") or []
        for index, label in enumerate(self.task_labels):
            if index < len(tasks):
                task = tasks[index]
                name = str(task.get("name") or "待确认任务")[:50]
                marker = task_review_label(task)
                label.setText(f"{name} · {fmt_seconds(int(task.get('engaged_seconds') or 0))} · {marker}")
                label.show()
            else:
                label.hide()
        interruptions = sum(
            event.get("event_type") == "non_work_interruption"
            for event in model.get("transitions") or []
        )
        if status == "disabled":
            message = "在设置中心开启本地任务分析"
        elif status == "unavailable":
            message = "任务证据暂不可读；原始记录不受影响"
        elif not tasks:
            message = "尚无足够的同口径工作会话"
        elif interruptions:
            message = f"本地关联到任务返回的插入事件 {interruptions} 次；不等于原有明显中断数"
        else:
            message = f"{len(tasks)} 个任务候选；自动识别无需确认，发现归属错误时可纠正"
        self.observation.setText(message)
