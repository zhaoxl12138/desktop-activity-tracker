"""Category stats page - progress bar + expandable top 5 apps per category."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QSignalBlocker, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHeaderView,
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services import category_stats_service
from ...utils import fmt_seconds
from ..dashboard_refresh_controller import DashboardRefreshController
from ..style import CATEGORY_COLOR_MAP, COLORS
from ..widgets.elided_label import ElidedLabel


class _CategoryCard(QFrame):
    clicked = Signal(str)

    def __init__(self, cat_key, cat_name, secs, total_eff, color):
        super().__init__()
        self._key = cat_key
        self._expanded = False
        self._color = color

        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet(
            f"_CategoryCard {{ background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']}; border-radius: 12px; }}"
            f"_CategoryCard:hover {{ border-color: {color}; }}"
        )

        self._main_layout = QVBoxLayout(self)
        self._main_layout.setContentsMargins(0, 0, 0, 0)
        self._main_layout.setSpacing(0)

        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(16, 10, 16, 10)
        row_layout.setSpacing(0)

        top_row = QWidget()
        top_layout = QVBoxLayout(top_row)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.setSpacing(0)

        header = QWidget()
        header_layout = QVBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(0)

        line = QFrame()
        line_layout = QVBoxLayout(line)
        line_layout.setContentsMargins(0, 0, 0, 0)
        line_layout.setSpacing(0)

        info = QWidget()
        from PySide6.QtWidgets import QHBoxLayout

        info_layout = QHBoxLayout(info)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(12)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        info_layout.addWidget(dot)

        self._name_lbl = ElidedLabel(cat_name)
        self._name_lbl.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self._name_lbl.setStyleSheet(f"color: {COLORS['text']};")
        self._name_lbl.setFixedWidth(90)
        info_layout.addWidget(self._name_lbl)

        pct = int(secs / total_eff * 100) if total_eff > 0 else 0
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(pct)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(16)
        self._bar.setStyleSheet(
            f"""
            QProgressBar {{ background: {COLORS['panel_bg']}; border: none; border-radius: 8px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 8px; }}
            """
        )
        info_layout.addWidget(self._bar, 1)

        self._time_lbl = QLabel(fmt_seconds(secs))
        self._time_lbl.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
        self._time_lbl.setFixedWidth(80)
        self._time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self._time_lbl)

        self._pct_lbl = QLabel(f"{pct}%")
        self._pct_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        self._pct_lbl.setFixedWidth(36)
        self._pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        info_layout.addWidget(self._pct_lbl)

        self._arrow = QLabel("▶")
        self._arrow.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        self._arrow.setFixedWidth(16)
        self._arrow.setAlignment(Qt.AlignCenter)
        info_layout.addWidget(self._arrow)

        line_layout.addWidget(info)
        header_layout.addWidget(line)
        top_layout.addWidget(header)
        row_layout.addWidget(top_row)
        self._main_layout.addWidget(row)

        self._detail = QFrame()
        self._detail.setStyleSheet(
            f"background: {COLORS['panel_bg_alt']}; border-top: 1px solid {COLORS['border']}; border-radius: 0 0 12px 12px;"
        )
        self._detail.hide()
        self._main_layout.addWidget(self._detail)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)

    def update_values(self, secs, total_eff, cat_name=None):
        pct = int(secs / total_eff * 100) if total_eff > 0 else 0
        if cat_name is not None:
            self._name_lbl.setText(str(cat_name))
        self._bar.setValue(pct)
        self._time_lbl.setText(fmt_seconds(secs))
        self._pct_lbl.setText(f"{pct}%")

    def set_expanded(self, expanded, detail_data=None, error_message=None, status_message=None):
        self._expanded = expanded
        self._arrow.setText("▼" if expanded else "▶")
        if expanded and detail_data is not None:
            self._build_detail(detail_data, error_message, status_message)
        self._detail.setVisible(expanded)

    def _build_detail(self, rows, error_message=None, status_message=None):
        layout = self._detail.layout()
        if layout is None:
            layout = QVBoxLayout(self._detail)
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        layout.setContentsMargins(40, 8, 16, 8)
        layout.setSpacing(4)

        if not rows:
            message = "  暂无记录"
            if error_message is not None:
                message = f"  明细读取失败：{error_message}" if error_message else "  明细读取失败"
            elif status_message is not None:
                message = f"  {status_message}"
            empty = QLabel(message)
            empty.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 12px;")
            layout.addWidget(empty)
            return

        table = QTableWidget()
        table.setColumnCount(3)
        table.setHorizontalHeaderLabels(["进程", "窗口标题", "时长"])
        table.horizontalHeader().setStretchLastSection(True)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.setColumnWidth(0, 140)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectRows)
        table.setRowCount(len(rows))
        table.setFixedHeight(30 * len(rows) + 28)

        for index, row in enumerate(rows):
            table.setItem(index, 0, QTableWidgetItem(row.get("process_name", "")))
            table.setItem(index, 1, QTableWidgetItem((row.get("window_title", "") or "-")[:60]))
            table.setItem(index, 2, QTableWidgetItem(fmt_seconds(row.get("effective_seconds", 0) or 0)))

        table.setStyleSheet(
            f"""
            QTableWidget {{
                background: transparent;
                color: {COLORS['text']};
                border: none;
                gridline-color: {COLORS['border']};
                font-size: 12px;
            }}
            QTableWidget::item {{ padding: 3px 6px; border: none; }}
            QTableWidget::item:selected {{ background: {COLORS['card_bg']}; }}
            QHeaderView::section {{
                background: transparent;
                color: {COLORS['text_muted']};
                border: none;
                padding: 4px 6px;
                font-weight: 700;
                font-size: 11px;
            }}
            """
        )
        layout.addWidget(table)


class CategoryStatsPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self._cards = {}
        self._category_details: dict[str, list[dict]] = {}
        self._expanded_key = None
        self._range_start = ""
        self._range_end = ""
        self._is_active = False
        self._last_signature = None
        self._empty_label: QLabel | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        period_row = QHBoxLayout()
        period_row.setSpacing(8)
        period_row.addWidget(QLabel("统计范围"))
        self.period_combo = QComboBox()
        for label, value in (("今天", "today"), ("近 7 天", "7d"),
                             ("近 30 天", "30d"), ("自定义", "custom")):
            self.period_combo.addItem(label, value)
        self.period_combo.setCurrentIndex(self.period_combo.findData("7d"))
        period_row.addWidget(self.period_combo)
        self.start_edit = QDateEdit(QDate.currentDate().addDays(-6))
        self.end_edit = QDateEdit(QDate.currentDate())
        for edit in (self.start_edit, self.end_edit):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
            edit.setEnabled(False)
        period_row.addWidget(self.start_edit)
        period_row.addWidget(QLabel("至"))
        period_row.addWidget(self.end_edit)
        period_row.addStretch(1)
        layout.addLayout(period_row)
        self._selection = ("7d", self.start_edit.date().toString("yyyy-MM-dd"),
                           self.end_edit.date().toString("yyyy-MM-dd"))

        self.error_lbl = QLabel()
        self.error_lbl.setStyleSheet(
            f"color: {COLORS['danger_red']}; font-size: 12px; background: {COLORS['error_bg']}; "
            f"border: 1px solid {COLORS['danger_red']}; border-radius: 6px; padding: 10px;"
        )
        self.error_lbl.hide()
        layout.addWidget(self.error_lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.cards_widget = QWidget()
        self.cards_widget.setStyleSheet("background: transparent;")
        self.cards_container = QVBoxLayout(self.cards_widget)
        self.cards_container.setContentsMargins(0, 0, 0, 0)
        self.cards_container.setSpacing(6)
        self.cards_container.addStretch()
        scroll.setWidget(self.cards_widget)
        layout.addWidget(scroll, 1)

        self.total_label = QLabel()
        self.total_label.setStyleSheet(f"font-size: 13px; color: {COLORS['text_secondary']}; padding: 4px 0;")
        layout.addWidget(self.total_label)

        self._refresh_controller = DashboardRefreshController(
            self._load_selected_summary,
            interval_ms=30_000,
            max_age_ms=30_000,
            parent=self,
        )
        self._refresh_controller.snapshot_ready.connect(
            lambda snapshot: self._apply_summary(snapshot.payload)
        )
        self._refresh_controller.failed.connect(self._show_refresh_error)
        self.timer = self._refresh_controller.timer
        self.period_combo.currentIndexChanged.connect(self._on_period_changed)
        self.start_edit.dateChanged.connect(self._on_period_changed)
        self.end_edit.dateChanged.connect(self._on_period_changed)

    def _selected_range(self) -> tuple[str, str]:
        today = QDate.currentDate()
        period = self.period_combo.currentData()
        if period == "today":
            start = end = today
        elif period == "7d":
            start, end = today.addDays(-6), today
        elif period == "30d":
            start, end = today.addDays(-29), today
        else:
            start, end = self.start_edit.date(), self.end_edit.date()
        span = start.daysTo(end)
        if not 0 <= span < 366:
            raise ValueError("日期范围必须为 1 至 366 天，且开始日期不能晚于结束日期")
        return start.toString("yyyy-MM-dd"), end.toString("yyyy-MM-dd")

    def _load_selected_summary(self) -> dict[str, object]:
        period, custom_start, custom_end = self._selection
        today = date.today()
        if period == "today":
            start = end = today.isoformat()
        elif period == "7d":
            start, end = (today - timedelta(days=6)).isoformat(), today.isoformat()
        elif period == "30d":
            start, end = (today - timedelta(days=29)).isoformat(), today.isoformat()
        else:
            start, end = custom_start, custom_end
        return category_stats_service.load_category_summary(self.db_path, start, end)

    def _refresh_expanded_detail(self) -> None:
        key = self._expanded_key
        card = self._cards.get(key) if key is not None else None
        if card is None:
            self._expanded_key = None
            return
        card.set_expanded(True, self._category_details.get(key, []))

    def _on_period_changed(self, *_args) -> None:
        period = self.period_combo.currentData()
        custom = period == "custom"
        if not custom:
            today = QDate.currentDate()
            start = today.addDays({"today": 0, "7d": -6, "30d": -29}[period])
            for edit, value in ((self.start_edit, start), (self.end_edit, today)):
                edit.blockSignals(True)
                edit.setDate(value)
                edit.blockSignals(False)
        self._selection = (
            str(period),
            self.start_edit.date().toString("yyyy-MM-dd"),
            self.end_edit.date().toString("yyyy-MM-dd"),
        )
        self.start_edit.setEnabled(custom)
        self.end_edit.setEnabled(custom)
        self._last_signature = None
        self._clear_all_cards()
        self.total_label.setText("加载中…")
        try:
            self._selected_range()
        except ValueError as exc:
            self._show_refresh_error(str(exc))
        else:
            self.error_lbl.hide()
        self._refresh_controller.invalidate_context()

    def activate(self, force: bool = False) -> None:
        self._is_active = True
        self._refresh_controller.set_foreground(True)
        if force:
            self._refresh_controller.request_refresh()

    def deactivate(self) -> None:
        self._is_active = False
        self._refresh_controller.set_foreground(False)

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.activate()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.deactivate()
        super().hideEvent(event)

    def refresh(self):
        """Synchronous compatibility hook used by tests and explicit tools."""
        if not self._is_active:
            return
        self.error_lbl.hide()
        try:
            summary = self._load_selected_summary()
            self._apply_summary(summary)
        except Exception as exc:
            self._show_refresh_error(str(exc))

    def _apply_summary(self, summary):
        self.error_lbl.hide()
        try:
            self._range_start = str(summary.get("range_start", summary["today"]))
            self._range_end = str(summary.get("range_end", summary["today"]))
            if self.period_combo.currentData() != "custom":
                for edit, day in ((self.start_edit, self._range_start),
                                  (self.end_edit, self._range_end)):
                    with QSignalBlocker(edit):
                        edit.setDate(QDate.fromString(day, "yyyy-MM-dd"))
            categories = list(summary["categories"])
            category_details = {
                str(key): [dict(row) for row in rows]
                for key, rows in (summary.get("category_details") or {}).items()
            }
            total_eff = int(summary["total_effective_seconds"])
            signature = (
                self._range_start,
                self._range_end,
                total_eff,
                tuple(
                    (item.get("category_key"), item.get("effective_seconds"), item.get("category_name"))
                    for item in categories
                ),
                tuple(
                    (
                        key,
                        tuple(
                            (
                                row.get("process_name"), row.get("window_title"),
                                row.get("effective_seconds"),
                            )
                            for row in rows
                        ),
                    )
                    for key, rows in sorted(category_details.items())
                ),
            )
            if signature == self._last_signature:
                return
            self._last_signature = signature
            self._category_details = category_details
            self.total_label.setText(str(summary["total_label"]))

            if not categories:
                self._clear_all_cards()
                self._empty_label = QLabel("暂无数据")
                self._empty_label.setStyleSheet(
                    f"color: {COLORS['text_muted']}; font-size: 14px;"
                )
                self._empty_label.setAlignment(Qt.AlignCenter)
                self.cards_container.insertWidget(0, self._empty_label)
                return

            self._clear_empty_state()
            new_keys = {category.get("category_key", "other") for category in categories}
            existing_keys = set(self._cards.keys())
            for key in existing_keys - new_keys:
                card = self._cards.pop(key, None)
                if card:
                    card.deleteLater()

            for category in reversed(categories):
                key = category.get("category_key", "other")
                name = category.get("category_name", "其他")
                secs = category.get("effective_seconds", 0) or 0
                if key in self._cards:
                    self._cards[key].update_values(secs, total_eff, name)
                else:
                    color = CATEGORY_COLOR_MAP.get(key, COLORS["idle_gray"])
                    card = _CategoryCard(key, name, secs, total_eff, color)
                    card.clicked.connect(self._on_card_clicked)
                    self._cards[key] = card
                    self.cards_container.insertWidget(0, card)

            # Existing cards keep their widgets, but their positions must be
            # rebuilt on every refresh so live duration changes also change
            # the visible ranking immediately.
            for category in reversed(categories):
                card = self._cards.get(category.get("category_key", "other"))
                if card is not None:
                    self.cards_container.removeWidget(card)
                    self.cards_container.insertWidget(0, card)
            if self._expanded_key is not None:
                self._refresh_expanded_detail()
        except Exception as exc:
            self._show_refresh_error(str(exc))

    def _show_refresh_error(self, message: str) -> None:
        self.error_lbl.setText(f"加载失败: {message}")
        self.error_lbl.show()

    def shutdown(self, timeout_ms: int = 5_000) -> bool:
        return self._refresh_controller.shutdown(timeout_ms)

    def resume(self) -> None:
        self._refresh_controller.resume(self._is_active)

    def _clear_all_cards(self):
        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        self._category_details = {}
        self._expanded_key = None
        self._empty_label = None
        self.cards_container.addStretch()

    def _clear_empty_state(self) -> None:
        if self._empty_label is None:
            return
        self.cards_container.removeWidget(self._empty_label)
        self._empty_label.deleteLater()
        self._empty_label = None

    def _on_card_clicked(self, cat_key):
        if self._expanded_key == cat_key:
            self._collapse_card(cat_key)
        else:
            if self._expanded_key:
                self._collapse_card(self._expanded_key)
            self._expand_card(cat_key)

    def _expand_card(self, cat_key):
        card = self._cards.get(cat_key)
        if not card:
            return
        self._expanded_key = cat_key
        self._refresh_expanded_detail()

    def _collapse_card(self, cat_key):
        card = self._cards.get(cat_key)
        if card:
            card.set_expanded(False)
        if self._expanded_key == cat_key:
            self._expanded_key = None
