"""Simple read-only full-day category lanes and chronological event details."""
from __future__ import annotations

import html
import queue
import threading
from datetime import date

from PySide6.QtCore import QEvent, QSignalBlocker, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QPushButton, QScrollArea, QTableView,
    QToolTip, QVBoxLayout, QWidget,
)

from ...utils import fmt_seconds
from .. import style
from .day_activity_category_timeline import DayActivityCategoryTimeline
from .day_activity_event_model import DayActivityEventModel


def coverage_label(model):
    """Coverage describes evidence completeness, not computer use or productivity."""
    status = model.get("status")
    if status == "loading":
        return "读取中"
    if status == "unavailable":
        return "读取失败"
    # The current read-only service exposes human-readable notes, not typed
    # issue codes. Exempt only its two known informational messages; unknown
    # warnings remain conservative. Legacy counters/name fallback do not mean
    # the foreground ranges are corrupt. All notes remain visible above.
    informational = {
        "包含旧版计时记录；有效时长保留，主动与被动时长不可确定。",
        "部分应用显示名称解析失败，已显示进程名。",
    }
    unreliable = any(message not in informational for message in model.get("warnings", []))
    if status == "empty" or not model.get("events"):
        return "含异常" if unreliable else "暂无记录"
    segments = sorted(model.get("segments", []), key=lambda item: item["start_second"])
    if unreliable or any(item.get("kind") == "unreliable" for item in segments):
        return "含异常"
    cursor, future = 0, False
    for item in segments:
        if item["start_second"] > cursor or item.get("kind") == "missing":
            return "部分覆盖"
        if item.get("kind") == "future":
            future = True
        cursor = max(cursor, item["end_second"])
    if cursor < 86400:
        return "部分覆盖"
    return "截至当前" if future else "完整覆盖"


class DayActivityDialog(QDialog):
    def __init__(self, db_path, day, days, *, sample_interval=1,
                 display_resolver=None, loader=None, parent=None):
        super().__init__(parent)
        if loader is None:
            from ...services.day_activity_service import load_day_activity
            loader = load_day_activity
        self._loader = loader
        self._db_path = str(db_path)
        self._sample_interval = sample_interval
        self._display_resolver = display_resolver
        self._results = queue.Queue()
        self._generation = 0
        self._inflight = False
        self._pending = None
        self._closed = False
        self._selected_event_id = None
        self.selected_category = None
        self.category_buttons = {}
        self.model = {"status": "loading", "events": [], "segments": []}
        self._visible_events = []
        self.setWindowTitle("全天活动详情")
        self.setStyleSheet(style.get_global_style() + style.get_input_style())
        available = self.screen().availableGeometry()
        self.resize(min(1180, int(available.width() * .9)), min(900, int(available.height() * .9)))
        self.setMinimumSize(min(620, int(available.width() * .9)),
                            min(420, int(available.height() * .9)))
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 12, 16, 12)
        root.setSpacing(8)
        header = QHBoxLayout()
        title = QLabel("全天活动详情")
        title.setStyleSheet(f"font-size: 21px; font-weight: 800; color: {style.COLORS['text']};")
        header.addWidget(title)
        header.addStretch()
        self.previous_button = QPushButton("‹")
        self.previous_button.setAccessibleName("前一天")
        header.addWidget(self.previous_button)
        self.day_picker = QComboBox()
        unique_days = sorted(set(days))
        if day not in unique_days:
            raise ValueError("所选日期不在图表日期范围内")
        for item in unique_days:
            parsed = date.fromisoformat(item)
            self.day_picker.addItem(f"{parsed.month}/{parsed.day} 周{'一二三四五六日'[parsed.weekday()]}", item)
        self.day_picker.setCurrentIndex(unique_days.index(day))
        self.day_picker.setAccessibleName("近7天日期")
        header.addWidget(self.day_picker)
        self.next_button = QPushButton("›")
        self.next_button.setAccessibleName("后一天")
        header.addWidget(self.next_button)
        self.refresh_button = QPushButton("刷新")
        header.addWidget(self.refresh_button)
        for button in (self.previous_button, self.next_button, self.refresh_button):
            button.setStyleSheet(style.get_button_secondary_style())
        self.previous_button.clicked.connect(lambda: self.day_picker.setCurrentIndex(self.day_picker.currentIndex() - 1))
        self.next_button.clicked.connect(lambda: self.day_picker.setCurrentIndex(self.day_picker.currentIndex() + 1))
        root.addLayout(header)
        self.status_label = QLabel()
        self.status_label.setTextFormat(Qt.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.setStyleSheet(f"color: {style.COLORS['text_secondary']};")
        root.addWidget(self.status_label)
        self.summary_label = QLabel()
        self.summary_label.setWordWrap(True)
        self.summary_label.setTextFormat(Qt.PlainText)
        self.summary_label.setStyleSheet(f"font-weight: 700; color: {style.COLORS['text']};")
        root.addWidget(self.summary_label)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self.scroll, 1)
        content = QWidget()
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 8, 0)
        self.body.setSpacing(10)
        self.scroll.setWidget(content)
        self.timeline = DayActivityCategoryTimeline()
        self.body.addWidget(self.timeline)
        self._timeline_help = "空闲／高空闲：留白　未来：点纹　异常：斜纹　无记录：底色（不等于空闲）"
        self.help_label = QLabel(self._timeline_help)
        self.help_label.setWordWrap(True)
        self.help_label.setStyleSheet(f"color: {style.COLORS['text_secondary']};")
        self.body.addWidget(self.help_label)

        event_panel = self._panel()
        event_layout = QVBoxLayout(event_panel)
        event_layout.setContentsMargins(14, 12, 14, 12)
        filters = QHBoxLayout()
        self.events_heading = QLabel("全天事件")
        self.events_heading.setStyleSheet("font-size: 15px; font-weight: 700;")
        filters.addWidget(self.events_heading)
        filters.addStretch()
        self.show_all = QCheckBox("显示全部事件")
        self.show_all.setStyleSheet(
            f"QCheckBox {{ background: transparent; color: {style.COLORS['text']}; spacing: 7px; }}"
            f"QCheckBox::indicator {{ width: 14px; height: 14px; border: 1px solid {style.COLORS['border_light']};"
            f" border-radius: 3px; background: {style.COLORS['panel_bg']}; }}"
            f"QCheckBox::indicator:checked {{ background: {style.COLORS['primary']}; border-color: {style.COLORS['primary']}; }}")
        filters.addWidget(self.show_all)
        event_layout.addLayout(filters)
        self.category_scroll = QScrollArea()
        self.category_scroll.setWidgetResizable(True)
        self.category_scroll.setFrameShape(QFrame.NoFrame)
        self.category_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.category_scroll.setFixedHeight(42)
        self.category_content = QWidget()
        self.category_layout = QHBoxLayout(self.category_content)
        self.category_layout.setContentsMargins(0, 0, 0, 0)
        self.category_layout.setSpacing(6)
        self.category_scroll.setWidget(self.category_content)
        event_layout.addWidget(self.category_scroll)
        self._category_group = QButtonGroup(self)
        self._category_group.setExclusive(True)
        self._populate_category_buttons()
        self.filter_hint = QLabel()
        self.filter_hint.setWordWrap(True)
        self.filter_hint.setStyleSheet(f"color: {style.COLORS['text_secondary']};")
        self.filter_hint.hide()
        event_layout.addWidget(self.filter_hint)
        self.events_table = QTableView()
        self.events_model = DayActivityEventModel(self.events_table)
        self.events_table.setModel(self.events_model)
        self.events_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.events_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.events_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.events_table.setWordWrap(False)
        self.events_table.setTextElideMode(Qt.ElideRight)
        self.events_table.setMinimumHeight(190)
        self.events_table.verticalHeader().hide()
        self.events_table.verticalHeader().setDefaultSectionSize(38)
        self.events_table.horizontalHeader().setStretchLastSection(False)
        self.events_table.horizontalHeader().setSectionResizeMode(QHeaderView.Fixed)
        self.events_table.horizontalHeader().setMinimumSectionSize(50)
        self.events_table.viewport().installEventFilter(self)
        self._resize_event_columns()
        event_layout.addWidget(self.events_table, 1)
        self.body.addWidget(event_panel, 1)

        self.events_table.selectionModel().selectionChanged.connect(lambda *_args: self._select_event())
        self.show_all.toggled.connect(self._render_events)
        self.timeline.event_activated.connect(self._activate_event)
        self.timeline.category_activated.connect(self._set_category)
        self.day_picker.currentIndexChanged.connect(self.refresh)
        self.refresh_button.clicked.connect(self.refresh)
        self._timer = QTimer(self)
        self._timer.setInterval(50)
        self._timer.timeout.connect(self._poll)
        self._timer.start()
        self.refresh()

    def eventFilter(self, watched, event):  # noqa: N802
        if watched is self.events_table.viewport() and event.type() == QEvent.Resize:
            self._resize_event_columns()
        return super().eventFilter(watched, event)

    def _resize_event_columns(self):
        """Reserve readable evidence columns instead of stretching titles forever."""
        if not hasattr(self, "events_table"):
            return
        viewport_width = self.events_table.viewport().width()
        other_minima = (110, 95, 90, 95, 75)
        title_minimum = 180
        minimum_total = sum(other_minima) + title_minimum
        if viewport_width <= minimum_total:
            widths = [110, 95, title_minimum, 90, 95, 75]
        else:
            title_width = min(440, int(viewport_width * .32), viewport_width - sum(other_minima))
            surplus = viewport_width - sum(other_minima) - title_width
            weights = (2, 2, 2, 1, 1)
            extras = [surplus * weight // sum(weights) for weight in weights]
            extras[-1] += surplus - sum(extras)
            widths = [other_minima[0] + extras[0], other_minima[1] + extras[1],
                      title_width, other_minima[2] + extras[2],
                      other_minima[3] + extras[3], other_minima[4] + extras[4]]
        for index, width in enumerate(widths):
            if self.events_table.columnWidth(index) != width:
                self.events_table.setColumnWidth(index, width)

    def _populate_category_buttons(self):
        while self.category_layout.count():
            item = self.category_layout.takeAt(0)
            if item.widget() is not None:
                self._category_group.removeButton(item.widget())
                item.widget().deleteLater()
        self.category_buttons = {}
        choices = (("all", "全部分类"),) + tuple(
            (lane["key"], lane["name"]) for lane in self.timeline.available_categories
        )
        for key, label in choices:
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                style.get_button_secondary_style()
                + "QPushButton { padding: 4px 10px; border-radius: 8px; font-size: 12px; }"
                + f"QPushButton:checked {{ background: {style.COLORS['primary']};"
                  f" border-color: {style.COLORS['primary']}; color: white; }}"
            )
            button.clicked.connect(lambda _checked=False, category=key:
                                   self._set_category(None if category == "all" else category))
            self._category_group.addButton(button)
            self.category_layout.addWidget(button)
            self.category_buttons[key] = button
        self.category_buttons["all"].setChecked(True)
        self.category_layout.addStretch(1)

    def _set_category(self, group):
        if group is not None and group not in self.category_buttons:
            return
        self.selected_category = group
        self.category_buttons[group or "all"].setChecked(True)
        self.timeline.set_category_filter(group)
        if (self._selected_event_id is not None
                and self.timeline.group_for_event(self._selected_event_id) != group
                and group is not None):
            self._selected_event_id = None
        self._render_events()

    @staticmethod
    def _panel():
        panel = QFrame()
        panel.setObjectName("dayActivityPanel")
        panel.setStyleSheet(f"QFrame#dayActivityPanel {{ background: {style.COLORS['card_bg_alt']};"
                            f" border: 1px solid {style.COLORS['border']}; border-radius: 12px; }}")
        return panel

    def refresh(self, *_args):
        if self._closed:
            return
        self._generation += 1
        day = self.day_picker.currentData()
        request = (self._generation, day)
        self.model = {"status": "loading", "day": day, "events": [], "segments": []}
        self.selected_category = None
        self._selected_event_id = None
        self.timeline.set_model(self.model)
        self._populate_category_buttons()
        self._visible_events = []
        self.events_model.set_events([])
        self.filter_hint.hide()
        self.help_label.setText(self._timeline_help)
        self.status_label.setText("正在读取所选日期的本地记录…")
        self.summary_label.setText("有效活动 — · 独立事件 —")
        self.previous_button.setEnabled(self.day_picker.currentIndex() > 0)
        self.next_button.setEnabled(self.day_picker.currentIndex() < self.day_picker.count() - 1)
        if self._inflight:
            self._pending = request
        else:
            self._launch(request)

    def _launch(self, request):
        self._inflight = True
        generation, day = request
        loader, db, results = self._loader, self._db_path, self._results
        interval, resolver = self._sample_interval, self._display_resolver

        def read():
            try:
                result = loader(db, day, sample_interval=interval, resolve_display=resolver)
                if not isinstance(result, dict):
                    raise ValueError("Invalid day activity result")
            except Exception:
                result = {"status": "unavailable", "day": day, "events": [], "segments": []}
            results.put((generation, day, result))

        # Only immutable arguments and a result queue cross the thread boundary.
        threading.Thread(target=read, name="DayLens-DayActivity", daemon=True).start()

    def _poll(self):
        if self._closed:
            return
        try:
            generation, day, result = self._results.get_nowait()
        except queue.Empty:
            return
        self._inflight = False
        if generation == self._generation and day == self.day_picker.currentData():
            self.model = result
            self._selected_event_id = None
            self.timeline.set_model(result)
            self.selected_category = None
            self._populate_category_buttons()
            self._display_status(result, day)
            totals = result.get("totals") or {}
            total = fmt_seconds(int(totals.get("effective_seconds") or 0))
            count = sum(int(item.get("effective_seconds") or 0) >= 300 for item in result.get("events", []))
            failed = result.get("status") == "unavailable"
            self.summary_label.setText("全天有效活动 — · 数据读取失败" if failed else
                                       f"全天有效活动 {total}　·　≥5分钟事件 {count} 个　·　{coverage_label(result)}")
            self._render_events()
        if self._pending is not None:
            request, self._pending = self._pending, None
            self._launch(request)

    def _display_status(self, result, day):
        parsed = date.fromisoformat(day)
        prefix = f"{parsed.year}年{parsed.month}月{parsed.day}日 · 星期{'一二三四五六日'[parsed.weekday()]}"
        message = {"unavailable": "读取失败，请点击刷新重试；正常记录不受影响。",
                   "empty": "暂无可展开的会话记录，不代表全天空闲。"}.get(result.get("status"), "")
        captured = str(result.get("captured_at") or "").replace("T", " ")
        last = str(result.get("last_recorded_at") or "").replace("T", " ")
        if not message:
            message = f"读取 {captured.split(' ')[-1] or '—'} · 最后记录 {last.split(' ')[-1] or '—'}"
        warnings = [str(item) for item in result.get("warnings", [])]
        if warnings:
            message += f"\n{warnings[0]}" + (f"（共{len(warnings)}项，悬停查看）" if len(warnings) > 1 else "")
        self.status_label.setText(prefix + "　" + message)
        details = f"{prefix}\n读取于 {captured or '—'}\n最后记录 {last or '—'}\n" + "\n".join(warnings)
        self.status_label.setToolTip("<qt>" + html.escape(details).replace("\n", "<br>") + "</qt>")

    def _render_events(self, *_args):
        events = self.model.get("events", [])
        self._visible_events = sorted((event for event in events
                                       if (self.selected_category is None
                                           or self.timeline.group_for_event(event["id"]) == self.selected_category)
                                       and (self.show_all.isChecked()
                                            or int(event.get("effective_seconds") or 0) >= 300)),
                                      key=lambda item: item["start_second"])
        suffix = "全部" if self.show_all.isChecked() else "有效 ≥5分钟"
        category = self.category_buttons.get(self.selected_category)
        category_name = category.text() if category is not None else "全部分类"
        self.events_heading.setText(f"全天事件 · {category_name} · {suffix}（{len(self._visible_events)}）")
        self.filter_hint.setText("今天没有有效活动达到5分钟的事件，可勾选“显示全部事件”查看短片段。")
        self.filter_hint.setVisible(bool(self.model.get("events") and not self._visible_events))
        with QSignalBlocker(self.events_table.selectionModel()):
            self.events_model.set_events(self._visible_events)
            row = self.events_model.row_for_id(self._selected_event_id)
            if row is not None:
                self.events_table.selectRow(row)
        self._highlight()

    def _highlight(self):
        self.timeline.select_event(self._selected_event_id)
        if self._selected_event_id and self.timeline.is_event_hidden(self._selected_event_id):
            if self.timeline.group_for_event(self._selected_event_id) == "idle":
                self.help_label.setText("空闲记录未在时间轴绘制；原始记录仍保留在事件明细中。")
            else:
                self.help_label.setText("此记录空闲占比超过70%，未在时间轴绘制；仍保留在事件明细和统计中。")
        else:
            self.help_label.setText(self._timeline_help)

    def _select_event(self):
        row = self.events_table.currentIndex().row()
        self._selected_event_id = self._visible_events[row]["id"] if 0 <= row < len(self._visible_events) else None
        self._highlight()

    def _activate_event(self, identity):
        event = next((item for item in self.model.get("events", []) if item["id"] == identity), None)
        if event is None:
            return
        self._selected_event_id = identity
        if int(event.get("effective_seconds") or 0) < 300:
            self.show_all.setChecked(True)
        self._render_events()
        row = self.events_model.row_for_id(identity)
        if row is not None:
            self.events_table.selectRow(row)
            self.events_table.scrollTo(self.events_model.index(row, 0))
            self.scroll.ensureWidgetVisible(self.events_table)

    def _stop_delivery(self):
        self._closed = True
        self._pending = None
        self._timer.stop()
        QToolTip.hideText()

    def done(self, result):
        self._stop_delivery()
        super().done(result)

    def closeEvent(self, event):  # noqa: N802
        self._stop_delivery()
        super().closeEvent(event)
