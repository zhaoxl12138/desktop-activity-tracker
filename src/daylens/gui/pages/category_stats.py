"""Category stats page — progress bar + expandable top 5 apps per category."""

from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame, QProgressBar,
    QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView, QSizePolicy
)
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont

from ... import database
from ...utils import fmt_seconds
from ..style import COLORS, CATEGORY_COLOR_MAP, get_category_color


class _CategoryCard(QFrame):
    """Clickable category card with expandable detail panel."""

    clicked = Signal(str)  # emits category_key

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

        # Main row
        self._main_layout = QHBoxLayout(self)
        self._main_layout.setContentsMargins(16, 10, 16, 10)
        self._main_layout.setSpacing(12)

        dot = QLabel()
        dot.setFixedSize(10, 10)
        dot.setStyleSheet(f"background: {color}; border-radius: 5px;")
        self._main_layout.addWidget(dot)

        name_lbl = QLabel(cat_name)
        name_lbl.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        name_lbl.setStyleSheet(f"color: {COLORS['text']};")
        name_lbl.setFixedWidth(90)
        self._main_layout.addWidget(name_lbl)

        pct = int(secs / total_eff * 100) if total_eff > 0 else 0
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(pct)
        bar.setTextVisible(False)
        bar.setFixedHeight(16)
        bar.setStyleSheet(f"""
            QProgressBar {{ background: {COLORS['panel_bg']}; border: none; border-radius: 8px; }}
            QProgressBar::chunk {{ background: {color}; border-radius: 8px; }}
        """)
        self._main_layout.addWidget(bar, 1)

        time_lbl = QLabel(fmt_seconds(secs))
        time_lbl.setStyleSheet(f"font-size: 13px; color: {COLORS['text']}; font-weight: 600;")
        time_lbl.setFixedWidth(80)
        time_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._main_layout.addWidget(time_lbl)

        pct_lbl = QLabel(f"{pct}%")
        pct_lbl.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        pct_lbl.setFixedWidth(36)
        pct_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._main_layout.addWidget(pct_lbl)

        # Expand arrow indicator
        self._arrow = QLabel("▶")
        self._arrow.setStyleSheet(f"font-size: 12px; color: {COLORS['text_muted']};")
        self._arrow.setFixedWidth(16)
        self._arrow.setAlignment(Qt.AlignCenter)
        self._main_layout.addWidget(self._arrow)

        # Detail panel (hidden by default)
        self._detail = QFrame()
        self._detail.setStyleSheet(
            f"background: {COLORS['panel_bg_alt']}; border-top: 1px solid {COLORS['border']};"
            f"border-radius: 0 0 12px 12px;"
        )
        self._detail.hide()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._key)
        super().mousePressEvent(event)

    def set_expanded(self, expanded, detail_data=None):
        self._expanded = expanded
        self._arrow.setText("▼" if expanded else "▶")
        if expanded and detail_data is not None:
            self._build_detail(detail_data)
        self._detail.setVisible(expanded)

    def _build_detail(self, rows):
        """Create the detail table from query_category_detail results."""
        # Clear existing content but keep the same frame (avoid floating window bug)
        old_layout = self._detail.layout()
        if old_layout is None:
            old_layout = QVBoxLayout(self._detail)
        while old_layout.count():
            item = old_layout.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()

        layout = old_layout
        layout.setContentsMargins(40, 8, 16, 8)
        layout.setSpacing(4)

        if not rows:
            empty = QLabel("  暂无记录")
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

        for i, r in enumerate(rows):
            pname = r.get("process_name", "")
            table.setItem(i, 0, QTableWidgetItem(pname))
            title = r.get("window_title", "") or "-"
            table.setItem(i, 1, QTableWidgetItem(title[:60]))
            secs = r.get("effective_seconds", 0) or 0
            table.setItem(i, 2, QTableWidgetItem(fmt_seconds(secs)))

        table.setStyleSheet(f"""
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
        """)
        layout.addWidget(table)


class CategoryStatsPage(QWidget):
    def __init__(self, db_path):
        super().__init__()
        self.db_path = db_path
        self._cards = {}          # cat_key -> _CategoryCard
        self._expanded_key = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        self.error_lbl = QLabel()
        self.error_lbl.setStyleSheet(
            f"color: {COLORS['danger_red']}; font-size: 12px;"
            f"background: #3A1620; border: 1px solid {COLORS['danger_red']};"
            f"border-radius: 6px; padding: 10px;"
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
        self.total_label.setStyleSheet(
            f"font-size: 13px; color: {COLORS['text_secondary']}; padding: 4px 0;"
        )
        layout.addWidget(self.total_label)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(30000)
        self.refresh()

    def refresh(self):
        # Remember expanded key before clearing
        expanded_key = self._expanded_key

        while self.cards_container.count():
            item = self.cards_container.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()
        self._expanded_key = None
        self.error_lbl.hide()

        today = datetime.now().strftime("%Y-%m-%d")
        try:
            stats = database.query_date_stats(self.db_path, today)
            categories = stats.get("by_category", [])

            total_eff = sum(c.get("effective_seconds", 0) or 0 for c in categories)
            self.total_label.setText(
                f"今日有效总计：{fmt_seconds(total_eff)}  |  {len(categories)} 个分类"
            )

            if not categories:
                no_data = QLabel("暂无数据")
                no_data.setStyleSheet(f"color: {COLORS['text_muted']}; font-size: 14px;")
                no_data.setAlignment(Qt.AlignCenter)
                self.cards_container.insertWidget(0, no_data)
                self.cards_container.addStretch()
                return

            # Re-populate cards
            for cat in reversed(categories):
                key = cat.get("category_key", "other")
                name = cat.get("category_name", "其他")
                secs = cat.get("effective_seconds", 0) or 0
                color = CATEGORY_COLOR_MAP.get(key, COLORS['idle_gray'])

                card = _CategoryCard(key, name, secs, total_eff, color)
                card.clicked.connect(self._on_card_clicked)
                self._cards[key] = card

                # Insert card above stretch
                # Build a wrapper to hold card + detail panel
                wrapper = QWidget()
                wrapper.setStyleSheet("background: transparent;")
                wl = QVBoxLayout(wrapper)
                wl.setContentsMargins(0, 0, 0, 0)
                wl.setSpacing(0)
                wl.addWidget(card)
                wl.addWidget(card._detail)
                self.cards_container.insertWidget(0, wrapper)

                # Restore expanded state after refresh
                if key == expanded_key:
                    self._expand_card(key)

            self.cards_container.addStretch()
        except Exception as e:
            import traceback
            self.error_lbl.setText(f"加载失败: {e}\n{traceback.format_exc()}")
            self.error_lbl.show()

    def _on_card_clicked(self, cat_key):
        if self._expanded_key == cat_key:
            self._collapse_card(cat_key)
            self._expanded_key = None
        else:
            if self._expanded_key:
                self._collapse_card(self._expanded_key)
            self._expand_card(cat_key)
            self._expanded_key = cat_key

    def _expand_card(self, cat_key):
        card = self._cards.get(cat_key)
        if not card:
            return
        today = datetime.now().strftime("%Y-%m-%d")
        try:
            detail = database.query_category_detail(self.db_path, today, cat_key, 5)
        except Exception:
            detail = []
        card.set_expanded(True, detail)

    def _collapse_card(self, cat_key):
        card = self._cards.get(cat_key)
        if card:
            card.set_expanded(False)
