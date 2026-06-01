"""Live monitor page for the current foreground session."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...utils import fmt_seconds
from ..style import COLORS, DASHBOARD_CARD_STYLE, TABLE_STYLE, get_category_color


class LiveMonitorPage(QWidget):
    """Realtime foreground-window monitor."""

    def __init__(self):
        super().__init__()
        self._samples = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(14)

        layout.addWidget(self._build_current_session_card())
        layout.addWidget(self._build_history_card(), 1)

    def _build_current_session_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)

        root = QVBoxLayout(card)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(12)

        title = QLabel("当前前台活动")
        title.setStyleSheet(f"font-size: 20px; font-weight: 800; color: {COLORS['text']};")
        header.addWidget(title)

        header.addStretch()

        self.lbl_status = QLabel("等待采样")
        self.lbl_status.setAlignment(Qt.AlignCenter)
        self.lbl_status.setStyleSheet(
            f"""
            QLabel {{
                color: {COLORS['text_muted']};
                background: {COLORS['panel_bg']};
                border: 1px solid {COLORS['border_light']};
                border-radius: 14px;
                padding: 5px 12px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        header.addWidget(self.lbl_status)
        root.addLayout(header)

        self.lbl_title = QLabel("--")
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setStyleSheet(
            f"font-size: 22px; font-weight: 800; color: {COLORS['text']};"
        )
        root.addWidget(self.lbl_title)

        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        self.lbl_process = self._make_badge("--", COLORS["primary"])
        self.lbl_category = self._make_badge("--", COLORS["idle_gray"])
        meta_row.addWidget(self.lbl_process)
        meta_row.addWidget(self.lbl_category)
        meta_row.addStretch()
        root.addLayout(meta_row)

        grid = QGridLayout()
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(12)

        self.lbl_duration = QLabel("--")
        self.lbl_effective = QLabel("--")
        self.lbl_session_idle = QLabel("--")
        self.lbl_idle = QLabel("--")

        cards = [
            ("前台停留", self.lbl_duration, COLORS["primary"]),
            ("有效时间", self.lbl_effective, COLORS["coding_green"]),
            ("本会话挂机", self.lbl_session_idle, COLORS["warning_yellow"]),
            ("系统空闲", self.lbl_idle, COLORS["idle_gray"]),
        ]
        for col, (label, value_label, color) in enumerate(cards):
            grid.addWidget(self._make_metric_tile(label, value_label, color), 0, col)
        root.addLayout(grid)

        return card

    def _build_history_card(self):
        card = QFrame()
        card.setObjectName("dashboardCard")
        card.setStyleSheet(DASHBOARD_CARD_STYLE)

        root = QVBoxLayout(card)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel("最近采样记录")
        title.setStyleSheet(f"font-size: 18px; font-weight: 800; color: {COLORS['text']};")
        root.addWidget(title)

        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels(["时间", "进程", "窗口标题", "分类", "有效"])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setStyleSheet(TABLE_STYLE)
        root.addWidget(self.table, 1)

        return card

    def _make_badge(self, text: str, color: str):
        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"""
            QLabel {{
                color: {color};
                background: #F8FAFF;
                border: 1px solid {COLORS['border_light']};
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        return label

    def _make_metric_tile(self, label_text: str, value_label: QLabel, color: str):
        tile = QFrame()
        tile.setStyleSheet(
            f"""
            QFrame {{
                background: #F8FAFF;
                border: 1px solid {COLORS['border_light']};
                border-radius: 14px;
            }}
            """
        )

        layout = QVBoxLayout(tile)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        label = QLabel(label_text)
        label.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"
        )
        layout.addWidget(label)

        value_label.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color};")
        layout.addWidget(value_label)
        return tile

    def on_sample_updated(self, sample):
        self._samples.insert(0, sample)
        if len(self._samples) > 20:
            self._samples = self._samples[:20]

        proc = sample.get("process_name", "--")
        title = (sample.get("window_title", "--") or "--")[:90]
        cat_name = sample.get("category_name", "--") or "--"
        cat_key = sample.get("category_key", "other") or "other"
        dur = sample.get("duration_seconds", 0) or 0
        eff = sample.get("effective_seconds", 0) or 0
        sidle = sample.get("session_idle_seconds", 0) or 0
        idle_s = sample.get("idle_seconds", 0) or 0
        category_color = get_category_color(cat_key)

        self.lbl_process.setText(proc)
        self.lbl_title.setText(title)
        self.lbl_category.setText(cat_name)
        self.lbl_category.setStyleSheet(
            f"""
            QLabel {{
                color: {category_color};
                background: #F8FAFF;
                border: 1px solid {COLORS['border_light']};
                border-radius: 13px;
                padding: 5px 10px;
                font-size: 12px;
                font-weight: 700;
            }}
            """
        )
        self.lbl_duration.setText(fmt_seconds(dur))
        self.lbl_effective.setText(fmt_seconds(eff))
        self.lbl_session_idle.setText(fmt_seconds(sidle))
        self.lbl_idle.setText(f"{idle_s:.0f}s")

        if sample.get("is_effective"):
            self.lbl_status.setText("有效记录中")
            self.lbl_status.setStyleSheet(
                f"""
                QLabel {{
                    color: {COLORS['success_green']};
                    background: #ECFDF5;
                    border: 1px solid #CFF7E2;
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )
        else:
            self.lbl_status.setText(f"挂机 {idle_s:.0f}s")
            self.lbl_status.setStyleSheet(
                f"""
                QLabel {{
                    color: {COLORS['warning_yellow']};
                    background: #FFF7ED;
                    border: 1px solid #FED7AA;
                    border-radius: 14px;
                    padding: 5px 12px;
                    font-size: 12px;
                    font-weight: 700;
                }}
                """
            )

        self.table.setRowCount(len(self._samples))
        for row, item in enumerate(self._samples):
            timestamp = item.get("timestamp", "")
            time_text = timestamp[-8:] if len(timestamp) >= 8 else timestamp
            normalized_title = item.get("normalized_title", "") or item.get("window_title", "")
            is_effective = "是" if item.get("is_effective") else "否"

            self.table.setItem(row, 0, QTableWidgetItem(time_text))
            self.table.setItem(row, 1, QTableWidgetItem(item.get("process_name", "")))
            self.table.setItem(row, 2, QTableWidgetItem(normalized_title))
            self.table.setItem(row, 3, QTableWidgetItem(item.get("category_name", "")))
            self.table.setItem(row, 4, QTableWidgetItem(is_effective))
