"""Daily goals workspace; existing GoalStore and accounting remain unchanged."""

from __future__ import annotations

import uuid
from datetime import date

from PySide6.QtCore import QDate, Qt, Signal
from PySide6.QtWidgets import (
    QDateEdit, QFrame, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QMenu, QMessageBox, QPushButton, QScrollArea, QToolButton, QVBoxLayout, QWidget,
)

from ...services.daily_goal_service import GOAL_CATEGORIES, GoalStore
from .. import style as ui_style
from ..widgets.goal_workspace_widgets import GoalEmptyState, GoalTile


_CATEGORIES = tuple((label, key) for key, label in GOAL_CATEGORIES.items())
_FIELDS = ("id", "type", "title", "target_kind", "target_id",
           "target_minutes", "confirmed", "confirmed_at")


def _metric(label: str) -> tuple[QFrame, QLabel]:
    frame = QFrame()
    frame.setObjectName("goalMetric")
    frame.setStyleSheet(
        f"QFrame#goalMetric {{ background: {ui_style.COLORS['card_bg_alt']}; "
        f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 10px; }}"
    )
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 10)
    caption = QLabel(label)
    caption.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};")
    value = QLabel("0")
    value.setStyleSheet(f"font-size: 23px; font-weight: 700; color: {ui_style.COLORS['text']};")
    layout.addWidget(caption)
    layout.addWidget(value)
    frame.setFixedHeight(84)
    return frame, value


def _subtle_button_style() -> str:
    return (
        f"QToolButton, QPushButton {{ background: {ui_style.COLORS['panel_bg_alt']}; "
        f"color: {ui_style.COLORS['text']}; border: 1px solid {ui_style.COLORS['border']}; "
        "border-radius: 7px; padding: 6px 10px; }"
    )


class DailyGoalsPage(QWidget):
    refresh_requested = Signal(str)

    def __init__(self, directory, parent=None):
        super().__init__(parent)
        self.store = GoalStore(directory)
        self.model = {"day": date.today().isoformat(), "status": "loading",
                      "revision": 0, "goals": []}
        self.available_tasks: list[dict] = []
        self.goal_cards: list[GoalTile] = []
        self._saving = False
        self._card_columns = 0
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("goalWorkspaceScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer.addWidget(scroll)
        self.content = QWidget()
        self.content.setObjectName("goalWorkspaceContent")
        self.content.setStyleSheet(
            f"QWidget#goalWorkspaceContent {{ background: {ui_style.COLORS['panel_bg']}; }}"
        )
        scroll.setWidget(self.content)
        body = QVBoxLayout(self.content)
        body.setContentsMargins(20, 18, 20, 18)
        body.setSpacing(14)
        body.setAlignment(Qt.AlignTop)

        header = QHBoxLayout()
        heading = QVBoxLayout()
        title = QLabel("目标与成果")
        title.setStyleSheet(f"font-size: 22px; font-weight: 700; color: {ui_style.COLORS['text']};")
        heading.addWidget(title)
        subtitle = QLabel("管理每天的投入与产出")
        subtitle.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text_secondary']};")
        heading.addWidget(subtitle)
        header.addLayout(heading)
        header.addStretch()
        self.new_goal_button = QPushButton()
        self.new_goal_button.setText("＋ 新建目标")
        self.new_goal_button.setAccessibleName("新建目标")
        self.new_goal_button.setStyleSheet(ui_style.get_button_primary_style())
        create_menu = QMenu(self.new_goal_button)
        create_menu.addAction("时间目标", self._add_time)
        create_menu.addAction("成果目标", self._add_outcome)
        self.new_goal_button.setMenu(create_menu)
        header.addWidget(self.new_goal_button)
        body.addLayout(header)

        toolbar = QHBoxLayout()
        self.prev_button = QToolButton()
        self.prev_button.setText("‹")
        self.prev_button.setAccessibleName("前一天")
        self.prev_button.setStyleSheet(_subtle_button_style())
        toolbar.addWidget(self.prev_button)
        self.day_picker = QDateEdit(QDate.currentDate())
        self.day_picker.setDisplayFormat("yyyy年M月d日")
        self.day_picker.setCalendarPopup(True)
        self.day_picker.setAccessibleName("目标日期")
        self.day_picker.setStyleSheet(
            f"QDateEdit {{ background: {ui_style.COLORS['panel_bg_alt']}; "
            f"color: {ui_style.COLORS['text']}; border: 1px solid {ui_style.COLORS['border']}; "
            "border-radius: 7px; padding: 6px 10px; }"
            f"QCalendarWidget {{ background: {ui_style.COLORS['panel_bg_alt']}; "
            f"color: {ui_style.COLORS['text']}; }}"
        )
        self.day_picker.dateChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.day_picker)
        self.next_button = QToolButton()
        self.next_button.setText("›")
        self.next_button.setAccessibleName("后一天")
        self.next_button.setStyleSheet(_subtle_button_style())
        toolbar.addWidget(self.next_button)
        self.today_button = QPushButton("今天")
        self.today_button.setStyleSheet(_subtle_button_style())
        toolbar.addWidget(self.today_button)
        self.prev_button.clicked.connect(lambda: self.day_picker.setDate(self.day_picker.date().addDays(-1)))
        self.next_button.clicked.connect(lambda: self.day_picker.setDate(self.day_picker.date().addDays(1)))
        self.today_button.clicked.connect(lambda: self.day_picker.setDate(QDate.currentDate()))
        toolbar.addStretch()
        self.limit_label = QLabel("每日上限 3 项")
        self.limit_label.setStyleSheet(f"color: {ui_style.COLORS['text_secondary']};")
        toolbar.addWidget(self.limit_label)
        self.refresh_button = QToolButton()
        self.refresh_button.setText("↻")
        self.refresh_button.setToolTip("刷新所选日期")
        self.refresh_button.setAccessibleName("刷新目标")
        self.refresh_button.setStyleSheet(_subtle_button_style())
        self.refresh_button.clicked.connect(lambda: self.refresh_requested.emit(self.selected_day()))
        toolbar.addWidget(self.refresh_button)
        body.addLayout(toolbar)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        for label, attr in (("目标数量", "summary_count"),
                            ("时间目标已达标", "summary_time"),
                            ("成果已确认", "summary_outcomes")):
            frame, value = _metric(label)
            setattr(self, attr, value)
            metrics.addWidget(frame, 1)
        body.addLayout(metrics)
        self.status = QLabel("正在加载目标…")
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"font-size: 13px; color: {ui_style.COLORS['text_secondary']};")
        body.addWidget(self.status)
        self.empty_state = GoalEmptyState()
        self.empty_time_button = self.empty_state.time_button
        self.empty_outcome_button = self.empty_state.outcome_button
        self.empty_state.add_time_requested.connect(self._add_time)
        self.empty_state.add_outcome_requested.connect(self._add_outcome)
        body.addWidget(self.empty_state)
        self.card_host = QWidget()
        self.card_grid = QGridLayout(self.card_host)
        self.card_grid.setContentsMargins(0, 0, 0, 0)
        self.card_grid.setSpacing(12)
        body.addWidget(self.card_host)
        self.empty_state.hide()
        self.card_host.hide()

    def selected_day(self) -> str:
        return self.day_picker.date().toString("yyyy-MM-dd")

    def activate(self, force: bool = False) -> None:
        self.refresh_requested.emit(self.selected_day())

    def deactivate(self) -> None:
        pass

    def set_available_tasks(self, model: dict) -> None:
        if model.get("day") == self.selected_day():
            self.available_tasks = [task for task in model.get("tasks") or []
                                    if task.get("status") == "confirmed"]

    def _on_date_changed(self, value: QDate) -> None:
        self.available_tasks = []
        self.model = {"day": value.toString("yyyy-MM-dd"), "status": "loading",
                      "revision": 0, "goals": []}
        self._render()
        self.refresh_requested.emit(self.selected_day())

    def set_model(self, model: dict) -> None:
        if model.get("day") != self.selected_day():
            return
        if model.get("status") == "unavailable" and self.model.get("day") == model.get("day"):
            model = {**model, "goals": self.model.get("goals") or []}
        self.model = model
        self._saving = False
        self._render()

    def _render(self) -> None:
        goals = self.model.get("goals") or []
        state = self.model.get("status")
        unknown = state in ("loading", "unavailable") and not goals
        self.summary_count.setText("— / 3" if unknown else f"{len(goals)} / 3")
        achieved = sum(
            goal.get("type") == "time_commitment"
            and goal.get("actual_seconds") is not None
            and int(goal["actual_seconds"]) >= int(goal.get("target_minutes") or 0) * 60
            for goal in goals
        )
        self.summary_time.setText("—" if unknown else str(achieved))
        self.summary_outcomes.setText("—" if unknown else str(sum(
            goal.get("type") == "outcome" and bool(goal.get("confirmed")) for goal in goals
        )))
        self.new_goal_button.setEnabled(state not in ("loading", "unavailable")
                                        and not self._saving and len(goals) < 3)
        empty_actions_enabled = state not in ("loading", "unavailable") and not self._saving
        self.empty_time_button.setEnabled(empty_actions_enabled)
        self.empty_outcome_button.setEnabled(empty_actions_enabled)
        self.new_goal_button.setToolTip("每天最多 3 项目标" if len(goals) >= 3 else "")
        self.status.setText(
            "正在加载所选日期目标…" if state == "loading"
            else "目标数据暂不可读；已停止写入。可尝试刷新。" if state == "unavailable"
            else "正在保存目标…" if self._saving
            else "今天尚无目标，最多设置 3 项" if not goals and self.selected_day() == date.today().isoformat()
            else "所选日期尚无目标" if not goals
            else "时间只统计可信主动参与；成果仅由你手动确认"
        )
        self.empty_state.title.setText(
            "今天还没有设置目标" if self.selected_day() == date.today().isoformat()
            else f"{self.selected_day()} 没有目标记录"
        )
        self.empty_state.setVisible(state not in ("loading", "unavailable") and not goals)
        self.card_host.setVisible(bool(goals))
        previous = {card.goal_id: card for card in self.goal_cards}
        old_order = [card.goal_id for card in self.goal_cards]
        updated_cards = []
        for goal in goals:
            goal_id = str(goal["id"])
            card = previous.pop(goal_id, None)
            if card is None:
                card = GoalTile(goal)
                card.edit_requested.connect(self._edit)
                card.delete_requested.connect(self._delete)
                card.confirm_requested.connect(self._toggle_outcome)
            else:
                card.set_goal(goal)
            card.setEnabled(state != "unavailable" and not self._saving)
            updated_cards.append(card)
        for card in previous.values():
            self.card_grid.removeWidget(card)
            card.deleteLater()
        self.goal_cards = updated_cards
        if old_order != [card.goal_id for card in updated_cards]:
            self._card_columns = 0
        self._arrange_cards()

    def _arrange_cards(self) -> None:
        columns = 2 if self.width() - 60 >= 680 else 1
        if columns == self._card_columns and self.card_grid.count() == len(self.goal_cards):
            return
        self._card_columns = columns
        while self.card_grid.count():
            self.card_grid.takeAt(0)
        for index, card in enumerate(self.goal_cards):
            self.card_grid.addWidget(card, index // columns, index % columns)
        for column in range(2):
            self.card_grid.setColumnStretch(column, 1 if column < columns else 0)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._arrange_cards()

    def _editable(self) -> bool:
        if self.model.get("status") == "unavailable":
            QMessageBox.information(self, "目标不可用", "目标文件暂不可读，已停止写入")
            return False
        if self.model.get("day") != self.selected_day() or self.model.get("status") == "loading":
            QMessageBox.information(self, "等待目标数据", "请等待所选日期加载完成")
            return False
        return not self._saving

    def _goals(self) -> list[dict]:
        return [{key: goal[key] for key in _FIELDS}
                for goal in self.model.get("goals") or []]

    def _save(self, goals: list[dict]) -> None:
        self._saving = True
        self._render()
        try:
            self.store.save_day(self.selected_day(), goals,
                                expected_revision=int(self.model.get("revision") or 0))
        except (RuntimeError, ValueError, OSError) as exc:
            self._saving = False
            self._render()
            QMessageBox.warning(self, "目标未保存", str(exc))
            return
        self.refresh_requested.emit(self.selected_day())

    def _add_time(self) -> None:
        if not self._editable():
            return
        goals = self._goals()
        if len(goals) >= 3:
            QMessageBox.information(self, "目标上限", "每天最多 3 项目标")
            return
        options = list(_CATEGORIES)
        choice, ok = QInputDialog.getItem(self, "时间目标", "选择分类",
                                          [label for label, _ in options], 0, False)
        if not ok:
            return
        target_id = dict(options)[choice]
        minutes, ok = QInputDialog.getInt(self, "计划投入", "分钟", 60, 1, 1440)
        if not ok:
            return
        goals.append({"id": "g-" + uuid.uuid4().hex, "type": "time_commitment",
                      "title": choice, "target_kind": "category",
                      "target_id": target_id, "target_minutes": minutes,
                      "confirmed": False, "confirmed_at": None})
        self._save(goals)

    def _add_outcome(self) -> None:
        if not self._editable():
            return
        goals = self._goals()
        if len(goals) >= 3:
            QMessageBox.information(self, "目标上限", "每天最多 3 项目标")
            return
        title, ok = QInputDialog.getText(self, "成果目标", "预期完成什么")
        if not ok or not title.strip():
            return
        goals.append({"id": "g-" + uuid.uuid4().hex, "type": "outcome",
                      "title": title.strip(), "target_kind": None, "target_id": None,
                      "target_minutes": None, "confirmed": False, "confirmed_at": None})
        self._save(goals)

    def _goal_by_id(self, goal_id: str) -> tuple[int, dict] | None:
        return next(((index, goal) for index, goal in enumerate(self.model.get("goals") or [])
                     if goal.get("id") == goal_id), None)

    def _edit(self, goal_id: str) -> None:
        if not self._editable():
            return
        selected = self._goal_by_id(goal_id)
        if selected is None:
            return
        index, goal = selected
        goals = self._goals()
        if goal["type"] == "time_commitment":
            keys = list(GOAL_CATEGORIES)
            current = keys.index(goal["target_id"]) if goal["target_id"] in keys else 0
            choice, ok = QInputDialog.getItem(self, "时间目标", "选择分类",
                                             list(GOAL_CATEGORIES.values()), current, False)
            if not ok:
                return
            minutes, ok = QInputDialog.getInt(self, "计划投入", "分钟",
                                              goal["target_minutes"], 1, 1440)
            if not ok:
                return
            goals[index]["target_minutes"] = minutes
            goals[index].update(title=choice, target_kind="category",
                                target_id=dict(_CATEGORIES)[choice])
        else:
            title, ok = QInputDialog.getText(self, "编辑目标", "目标名称", text=goal["title"])
            if not ok or not title.strip():
                return
            goals[index]["title"] = title.strip()
        self._save(goals)

    def _delete(self, goal_id: str) -> None:
        if not self._editable():
            return
        selected = self._goal_by_id(goal_id)
        if selected is None:
            return
        index, goal = selected
        dialog = QMessageBox(QMessageBox.Question, "删除目标",
                             f"确定删除目标“{goal['title']}”？",
                             QMessageBox.Yes | QMessageBox.No, self)
        dialog.setTextFormat(Qt.PlainText)
        if dialog.exec() != QMessageBox.Yes:
            return
        goals = self._goals()
        del goals[index]
        self._save(goals)

    def _toggle_outcome(self, goal_id: str) -> None:
        if not self._editable():
            return
        selected = self._goal_by_id(goal_id)
        if selected is None:
            return
        _index, goal = selected
        if goal["type"] != "outcome":
            QMessageBox.information(self, "时间目标", "时间目标只比较投入，不表示成果完成")
            return
        self._saving = True
        self._render()
        try:
            self.store.confirm_outcome(
                self.selected_day(), goal["id"], not goal["confirmed"],
                expected_revision=int(self.model.get("revision") or 0),
            )
        except (RuntimeError, ValueError, OSError) as exc:
            self._saving = False
            self._render()
            QMessageBox.warning(self, "成果确认未保存", str(exc))
            return
        self.refresh_requested.emit(self.selected_day())
