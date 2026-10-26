"""Task evidence and reversible corrections inside the existing Statistics page."""

from __future__ import annotations

import json
import uuid
from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QDateEdit, QDialog, QDialogButtonBox, QHBoxLayout,
    QInputDialog, QLabel, QListWidget, QListWidgetItem, QMessageBox,
    QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)

from ...services.task_decision_service import TaskDecisionStore
from ...services.task_intelligence_service import PROMPT, prepare_task_payload
from ...services.task_insights_service import task_review_label
from ...utils import fmt_seconds


class TaskChainPage(QWidget):
    refresh_requested = Signal(str)
    cloud_approved = Signal(object, str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.directory = directory
        self.model = {"status": "disabled", "tasks": [], "transitions": [],
                      "evidence": {}, "revision": 0, "day": date.today().isoformat()}
        self.ai_suggestions = {}
        outer = QVBoxLayout(self)
        controls = QHBoxLayout()
        controls.addWidget(QLabel("日期"))
        self.day_picker = QDateEdit(QDate.currentDate())
        self.day_picker.setCalendarPopup(True)
        self.day_picker.dateChanged.connect(
            lambda value: self.refresh_requested.emit(value.toString("yyyy-MM-dd"))
        )
        controls.addWidget(self.day_picker)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(lambda: self.refresh_requested.emit(self.selected_day()))
        controls.addWidget(self.refresh_button)
        controls.addStretch()
        outer.addLayout(controls)
        self.status = QLabel("在设置中心开启本地任务分析")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        outer.addWidget(self.status)
        self.tasks_table = QTableWidget(0, 4)
        self.tasks_table.setHorizontalHeaderLabels(["任务候选", "参与时长", "状态", "会话"])
        self.tasks_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tasks_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tasks_table.verticalHeader().hide()
        self.tasks_table.horizontalHeader().setStretchLastSection(True)
        self.tasks_table.itemSelectionChanged.connect(self._show_selected_task)
        outer.addWidget(self.tasks_table, 2)
        outer.addWidget(QLabel("原始会话依据（可多选，用于拆分或移动）"))
        self.evidence_list = QListWidget()
        self.evidence_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        outer.addWidget(self.evidence_list, 2)
        outer.addWidget(QLabel("任务级切换观察（与原有“明显中断”口径不同）"))
        self.events_list = QListWidget()
        outer.addWidget(self.events_list, 1)
        buttons = QHBoxLayout()
        self.action_buttons = {}
        for text, action in (("确认", "confirm"), ("改名", "rename"),
                             ("拆分", "split"), ("合并", "merge"),
                             ("移动会话", "move"), ("忽略", "ignore"),
                             ("撤销", "undo")):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, selected=action: self._action(selected))
            buttons.addWidget(button)
            self.action_buttons[action] = button
        outer.addLayout(buttons)
        self.ai_button = QPushButton("预览云端任务建议")
        self.ai_button.clicked.connect(self._preview_cloud)
        outer.addWidget(self.ai_button)
        self.ai_result = QLabel("")
        self.ai_result.setTextFormat(Qt.PlainText)
        self.ai_result.setWordWrap(True)
        outer.addWidget(self.ai_result)

    def selected_day(self) -> str:
        return self.day_picker.date().toString("yyyy-MM-dd")

    def activate(self, force: bool = False) -> None:
        self.refresh_requested.emit(self.selected_day())

    def deactivate(self) -> None:
        pass

    def set_model(self, model: dict) -> None:
        self.model = model
        self.ai_suggestions = {}
        self.status.setText({
            "disabled": "本地任务分析未开启；原始统计照常运行",
            "ready": "本地统计 · 自动识别无需确认；人工操作仅用于纠正或固定归属",
            "insufficient_data": "同口径任务证据不足",
            "unavailable": "任务状态暂不可读；原始记录不受影响",
        }.get(model.get("status"), "等待确认"))
        tasks = model.get("tasks") or []
        self.tasks_table.setRowCount(len(tasks))
        for index, task in enumerate(tasks):
            values = (self._task_name(task),
                      fmt_seconds(int(task.get("engaged_seconds") or 0)),
                      task_review_label(task),
                      str(len(task.get("source_session_ids") or [])))
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                self.tasks_table.setItem(index, column, item)
        self.ai_button.setEnabled(bool(model.get("cloud_enabled") and tasks))
        if tasks:
            self.tasks_table.selectRow(0)
        self._show_selected_task()

    def _selected_task(self) -> dict | None:
        index = self.tasks_table.currentRow()
        tasks = self.model.get("tasks") or []
        return tasks[index] if 0 <= index < len(tasks) else None

    def _task_name(self, task: dict) -> str:
        suggestion = self.ai_suggestions.get(str(task.get("id") or ""), {})
        return str(suggestion.get("suggested_name") or task.get("name") or "未命名工作")

    def _show_selected_task(self) -> None:
        self.evidence_list.clear()
        self.events_list.clear()
        task = self._selected_task()
        self.action_buttons["confirm"].setText(
            "确认" if task and task.get("review_status") == "needs_confirmation"
            else "固定此任务（可选）"
        )
        if task is None:
            return
        evidence = self.model.get("evidence") or {}
        for identity in task.get("source_session_ids") or []:
            row = evidence.get(identity, {})
            item = QListWidgetItem(
                f"{row.get('start_time', '')}–{row.get('end_time', '')} · "
                f"{row.get('app', '')} · {row.get('title', '')} · "
                f"参与 {fmt_seconds(int(row.get('engaged_seconds') or 0))}"
            )
            item.setData(Qt.UserRole, identity)
            self.evidence_list.addItem(item)
        for event in self.model.get("transitions") or []:
            if event.get("source_task_id") != task["id"]:
                continue
            kind = {"workflow_switch": "工作流工具切换", "task_switch": "任务切换",
                    "non_work_interruption": "非工作活动插入并返回"}.get(
                        event.get("event_type"), "用途待确认的切换")
            refs = ", ".join(
                f"{evidence.get(identity, {}).get('app', '')} · "
                f"{evidence.get(identity, {}).get('title', '')}"
                for identity in event.get("interruption_session_ids") or []
            )
            self.events_list.addItem(f"{kind} · 会话依据 {refs or '相邻工作会话'}")

    def _selected_session_ids(self) -> list[str]:
        return [str(item.data(Qt.UserRole)) for item in self.evidence_list.selectedItems()]

    def _choose_target(self, source_id: str) -> str | None:
        options = [task for task in self.model.get("tasks") or [] if task["id"] != source_id]
        if not options:
            return None
        labels = [f"{task.get('name') or '待确认任务'} ({task['id'][:8]})" for task in options]
        choice, ok = QInputDialog.getItem(self, "选择目标任务", "目标任务", labels, 0, False)
        return options[labels.index(choice)]["id"] if ok else None

    def _action(self, action: str) -> None:
        if self.model.get("day") != self.selected_day() or self.model.get("status") != "ready":
            QMessageBox.information(self, "等待任务数据", "请等待所选日期的任务链加载完成")
            return
        task = self._selected_task()
        if action != "undo" and task is None:
            return
        try:
            store = TaskDecisionStore(self.directory)
            revision = int(self.model.get("revision") or 0)
            if action == "undo":
                store.undo(expected_revision=revision)
            else:
                task_id = task["id"]
                ids = list(task["source_session_ids"])
                name = ""
                if action == "confirm":
                    name = self._task_name(task)
                elif action in {"rename", "split"}:
                    name, ok = QInputDialog.getText(
                        self, "任务名称", "请确认任务名", text=self._task_name(task)
                    )
                    if not ok or not name.strip():
                        return
                if action == "rename":
                    ids = []
                elif action == "split":
                    ids = self._selected_session_ids()
                    if not ids or len(ids) >= len(task["source_session_ids"]):
                        raise ValueError("请选择部分（而非全部）会话进行拆分")
                    task_id = "manual-" + uuid.uuid4().hex
                elif action in {"merge", "move"}:
                    if action == "move":
                        ids = self._selected_session_ids()
                        if not ids:
                            raise ValueError("请先选择要移动的会话")
                    task_id = self._choose_target(task["id"])
                    if task_id is None:
                        return
                elif action == "ignore":
                    ids = []
                state = store.apply(
                    action, ids, task_id, name.strip(), expected_revision=revision
                )
                self.model["revision"] = state["revision"]
                if action in {"confirm", "rename"}:
                    task["name"] = name.strip()
                    task["name_source"] = "manual"
                    if action == "confirm":
                        task["status"] = "confirmed"
                        task["review_status"] = "confirmed"
                    row = self.tasks_table.currentRow()
                    if row >= 0:
                        self.tasks_table.item(row, 0).setText(name.strip())
                        self.tasks_table.item(row, 2).setText(
                            task_review_label(task)
                        )
            self.refresh_requested.emit(self.selected_day())
        except (RuntimeError, ValueError, OSError) as exc:
            QMessageBox.warning(self, "任务纠正未保存", str(exc))

    def _preview_cloud(self) -> None:
        if (not self.model.get("cloud_enabled")
                or self.model.get("day") != self.selected_day()):
            return
        rows = []
        for identity, value in (self.model.get("evidence") or {}).items():
            rows.append({"session_id": identity, "process_name": value.get("app"),
                         "normalized_title": value.get("title")})
        prepared = prepare_task_payload(rows, self.model)
        if not prepared["payload"]["candidates"]:
            QMessageBox.information(self, "证据不足", "目前没有适合发送的任务候选")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("预览实际发送给 DeepSeek 的内容")
        dialog.resize(600, 420)
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel("仅本次发送。请检查下列实际载荷；取消不会调用 API 或扣费。"))
        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(
            "指令：\n" + PROMPT + "\n\n数据：\n"
            + json.dumps(prepared["payload"], ensure_ascii=False, indent=2)
        )
        layout.addWidget(preview)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("确认发送")
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.Accepted:
            self.cloud_approved.emit(prepared, prepared["digest"])

    def set_ai_suggestions(self, items: list[dict] | None, message: str = "") -> None:
        if not items:
            self.ai_result.setText(message or "云端建议未生成；本地任务链仍可使用")
            return
        task_ids = {str(task.get("id") or "") for task in self.model.get("tasks") or []}
        self.ai_suggestions = {
            str(item.get("candidate_id")): dict(item)
            for item in items
            if (str(item.get("candidate_id") or "") in task_ids
                and str(item.get("suggested_name") or "").strip())
        }
        for row, task in enumerate(self.model.get("tasks") or []):
            cell = self.tasks_table.item(row, 0)
            if cell is not None:
                cell.setText(self._task_name(task))
        names = {task["id"]: task.get("name") or task["id"][:8]
                 for task in self.model.get("tasks") or []}
        self.ai_result.setText("；".join(
            f"AI 建议：{item['suggested_name']}（{item['confidence']}，需人工确认）"
            + (" · 可能关联 " + "、".join(names.get(identity, identity[:8])
                                      for identity in item.get("related_candidate_ids") or [])
               + "（未合并）" if item.get("related_candidate_ids") else "")
            for item in items
        ))
