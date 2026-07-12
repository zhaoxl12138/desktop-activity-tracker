"""Reports center - generate, select, open, download, and sync reports."""

from __future__ import annotations

import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services import reports_service
from .. import style as ui_style


class ReportsPage(QWidget):
    def __init__(self, db_path, reports_dir, obsidian_path=""):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.obsidian_path = obsidian_path
        self.selected_report: dict | None = None
        self.selected_reports: list[dict] = []
        self._is_active = False
        self._last_signature = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("报告中心")
        title.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(title)

        subtitle = QLabel("生成、查看和导出你的时间报告。")
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        layout.addWidget(subtitle)
        layout.addWidget(self._build_generation_bar())

        content = QHBoxLayout()
        content.setSpacing(14)
        content.addWidget(self._build_report_list(), 1)
        content.addWidget(self._build_detail_panel())
        layout.addLayout(content, 1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.setInterval(60000)

    def activate(self, force: bool = False) -> None:
        self._is_active = True
        if not self.timer.isActive():
            self.timer.start()
        if force or self._last_signature is None:
            self.refresh()

    def deactivate(self) -> None:
        self._is_active = False
        self.timer.stop()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.activate()

    def hideEvent(self, event) -> None:  # noqa: N802
        self.deactivate()
        super().hideEvent(event)

    def _build_generation_bar(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("dashboardCard")
        frame.setStyleSheet(ui_style.get_dashboard_card_style())
        row = QHBoxLayout(frame)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)

        label = QLabel("生成报告")
        label.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        row.addWidget(label)

        self.btn_daily = self._button("今日日报", self._generate_daily, primary=True)
        self.btn_weekly = self._button("本周周报", self._generate_weekly, primary=True)
        self.btn_monthly = self._button("本月月报", self._generate_monthly, primary=True)
        row.addWidget(self.btn_daily)
        row.addWidget(self.btn_weekly)
        row.addWidget(self.btn_monthly)
        row.addStretch()

        self.btn_open_dir = self._button("打开报告目录", self._open_reports_dir)
        row.addWidget(self.btn_open_dir)
        return frame

    def _build_report_list(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reportListCard")
        frame.setStyleSheet(
            f"""
            QFrame#reportListCard {{
                background: {ui_style.COLORS['card_bg']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 14px;
            }}
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            f"""
            QTabWidget::pane {{
                border: none;
                background: transparent;
            }}
            QTabBar::tab {{
                min-width: 86px;
                padding: 9px 18px;
                margin-right: 6px;
                color: {ui_style.COLORS['text_secondary']};
                background: {ui_style.COLORS['panel_bg']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 9px;
                font-size: 13px;
                font-weight: 700;
            }}
            QTabBar::tab:selected {{
                color: {ui_style.COLORS['text_inverse']};
                background: {ui_style.COLORS['primary']};
                border-color: {ui_style.COLORS['primary']};
            }}
            QTabBar::tab:hover:!selected {{
                color: {ui_style.COLORS['text']};
                border-color: {ui_style.COLORS['primary']};
            }}
            """
        )

        self.tab_daily = self._make_table()
        self.tab_weekly = self._make_table()
        self.tab_monthly = self._make_table()
        self.tabs.addTab(self.tab_daily, "日报")
        self.tabs.addTab(self.tab_weekly, "周报")
        self.tabs.addTab(self.tab_monthly, "月报")
        self.tabs.currentChanged.connect(self._clear_selection)
        layout.addWidget(self.tabs)
        return frame

    def _build_detail_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("reportDetailCard")
        frame.setMinimumWidth(240)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        frame.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        frame.setStyleSheet(
            f"""
            QFrame#reportDetailCard {{
                background: {ui_style.COLORS['card_bg_alt']};
                border: 1px solid {ui_style.COLORS['border_light']};
                border-radius: 14px;
            }}
            """
        )
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        eyebrow = QLabel("当前选中")
        eyebrow.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        layout.addWidget(eyebrow)

        self.detail_title = QLabel("选择一份报告")
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(
            f"font-size: 20px; font-weight: 800; color: {ui_style.COLORS['text']};"
        )
        layout.addWidget(self.detail_title)

        self.detail_meta = QLabel("从左侧列表选择报告后，可以下载、打开或同步。")
        self.detail_meta.setWordWrap(True)
        self.detail_meta.setStyleSheet(
            f"font-size: 13px; line-height: 1.7; color: {ui_style.COLORS['text_secondary']};"
        )
        layout.addWidget(self.detail_meta)
        layout.addStretch()

        self.btn_download = self._button("下载 Markdown", self._download_selected, primary=True)
        self.btn_open = self._button("打开报告", self._open_selected)
        self.btn_sync_selected = self._button("同步到 Obsidian", self._sync_selected)
        layout.addWidget(self.btn_download)
        layout.addWidget(self.btn_open)
        layout.addWidget(self.btn_sync_selected)
        self._set_action_enabled(False)
        return frame

    def _button(self, text: str, callback, primary: bool = False) -> QPushButton:
        button = QPushButton(text)
        button.setCursor(Qt.PointingHandCursor)
        base_style = (
            ui_style.get_button_primary_style()
            if primary
            else ui_style.get_button_secondary_style()
        )
        button.setStyleSheet(
            base_style
            + f"""
            QPushButton:disabled {{
                background: {ui_style.COLORS['panel_bg']};
                color: {ui_style.COLORS['text_muted']};
                border: 1px solid {ui_style.COLORS['border']};
            }}
            """
        )
        button.clicked.connect(callback)
        return button

    def _make_table(self) -> QTableWidget:
        table = QTableWidget()
        table.setColumnCount(4)
        table.setHorizontalHeaderLabels(["日期 / 标识", "文件名", "大小", "更新时间"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table.setAlternatingRowColors(True)
        table.setShowGrid(False)
        table.setStyleSheet(
            ui_style.get_table_style()
            + f"""
            QTableWidget::item {{
                padding: 10px 8px;
            }}
            QTableWidget::item:selected {{
                background: {ui_style.COLORS['primary']};
                color: {ui_style.COLORS['text_inverse']};
            }}
            """
        )
        table.itemSelectionChanged.connect(lambda current=table: self._select_from_table(current))
        table.itemDoubleClicked.connect(self._open_selected)
        return table

    def refresh(self):
        table_specs = [
            (self.tab_daily, "daily", "日报"),
            (self.tab_weekly, "weekly", "周报"),
            (self.tab_monthly, "monthly", "月报"),
        ]
        for index, (table, subdir, title) in enumerate(table_specs):
            rows = reports_service.list_report_rows(self.reports_dir, subdir, limit=50)
            signature = tuple(
                (row.get("filename"), row.get("size_text"), row.get("modified_text"))
                for row in rows
            )
            if self._last_signature is not None and self._last_signature[index] == signature:
                continue
            table.blockSignals(True)
            table.clearContents()
            table.setRowCount(len(rows))
            for row_index, report in enumerate(rows):
                label_item = QTableWidgetItem(report["label"])
                label_item.setData(Qt.UserRole, report)
                table.setItem(row_index, 0, label_item)
                table.setItem(row_index, 1, QTableWidgetItem(report["filename"]))
                table.setItem(row_index, 2, QTableWidgetItem(report["size_text"]))
                table.setItem(row_index, 3, QTableWidgetItem(report["modified_text"]))
                table.setRowHeight(row_index, 46)
            table.clearSelection()
            table.blockSignals(False)
            self.tabs.setTabText(index, f"{title}  {len(rows)}")
            if self._last_signature is None:
                self._last_signature = [None, None, None]
            self._last_signature[index] = signature
        self._clear_selection()

    def _select_from_table(self, table: QTableWidget) -> None:
        if table is not self.tabs.currentWidget():
            return
        selected_rows = table.selectionModel().selectedRows()
        if not selected_rows:
            self._clear_selection()
            return
        reports = []
        for index in sorted(selected_rows, key=lambda item: item.row()):
            item = table.item(index.row(), 0)
            report = item.data(Qt.UserRole) if item is not None else None
            if report:
                reports.append(report)
        if not reports:
            self._clear_selection()
            return
        self.selected_reports = reports
        if len(reports) == 1:
            report = reports[0]
            self.selected_report = report
            self.detail_title.setText(report["label"])
            self.detail_meta.setText(
                "\n".join(
                    [
                        f"类型：{report['report_type']}",
                        f"文件：{report['filename']}",
                        f"大小：{report['size_text']}",
                        f"更新：{report['modified_text']}",
                        "格式：Markdown",
                    ]
                )
            )
            self.btn_download.setText("下载 Markdown")
            self._set_action_enabled(True, allow_single_actions=True)
            return

        self.selected_report = None
        total_bytes = sum(
            os.path.getsize(report["file_path"])
            for report in reports
            if os.path.isfile(report["file_path"])
        )
        total_kb = max(1, (total_bytes + 1023) // 1024)
        self.detail_title.setText(f"已选择 {len(reports)} 份报告")
        self.detail_meta.setText(
            "\n".join(
                [
                    f"合计大小：{total_kb} KB",
                    "格式：Markdown",
                    "批量下载将保留原文件名。",
                    "同名文件会自动添加序号。",
                ]
            )
        )
        self.btn_download.setText(f"批量下载（{len(reports)}）")
        self._set_action_enabled(True, allow_single_actions=False)

    def _clear_selection(self, *_args) -> None:
        self.selected_report = None
        self.selected_reports = []
        self.detail_title.setText("选择一份报告")
        self.detail_meta.setText("从左侧列表选择报告后，可以下载、打开或同步。")
        self.btn_download.setText("下载 Markdown")
        self._set_action_enabled(False, allow_single_actions=False)

    def _set_action_enabled(self, enabled: bool, allow_single_actions: bool = True) -> None:
        self.btn_download.setEnabled(enabled)
        self.btn_open.setEnabled(enabled and allow_single_actions)
        self.btn_sync_selected.setEnabled(enabled and allow_single_actions)

    def _selected_path(self) -> str | None:
        if not self.selected_report:
            return None
        return self.selected_report.get("file_path")

    def _download_selected(self) -> None:
        if len(self.selected_reports) > 1:
            self._download_multiple()
            return
        source_path = self._selected_path()
        if not source_path:
            return
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")
        suggested_path = os.path.join(downloads_dir, self.selected_report["filename"])
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "下载报告",
            suggested_path,
            "Markdown 文件 (*.md)",
        )
        if not destination:
            return
        if not destination.lower().endswith(".md"):
            destination += ".md"
        try:
            saved_path = reports_service.download_report(source_path, destination)
            QMessageBox.information(self, "下载完成", f"报告已保存到\n{saved_path}")
        except Exception as exc:
            QMessageBox.warning(self, "下载失败", str(exc))

    def _download_multiple(self) -> None:
        downloads_dir = os.path.join(os.path.expanduser("~"), "Downloads")
        if not os.path.isdir(downloads_dir):
            downloads_dir = os.path.expanduser("~")
        destination = QFileDialog.getExistingDirectory(
            self,
            "选择批量下载目录",
            downloads_dir,
        )
        if not destination:
            return
        try:
            result = reports_service.download_reports(
                [report["file_path"] for report in self.selected_reports],
                destination,
            )
            message = "\n".join(
                [
                    f"成功：{result['success_count']} 份",
                    f"自动重命名：{result['renamed_count']} 份",
                    f"失败：{result['failure_count']} 份",
                    f"保存目录：{result['destination_dir']}",
                ]
            )
            if result["failure_count"]:
                QMessageBox.warning(self, "批量下载完成", message)
            else:
                QMessageBox.information(self, "批量下载完成", message)
        except Exception as exc:
            QMessageBox.warning(self, "批量下载失败", str(exc))

    def _open_selected(self, *_args) -> None:
        file_path = self._selected_path()
        if not file_path:
            return
        try:
            reports_service.open_report(file_path)
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))
            self.refresh()

    def _open_reports_dir(self) -> None:
        try:
            os.makedirs(self.reports_dir, exist_ok=True)
            reports_service.open_report(self.reports_dir)
        except Exception as exc:
            QMessageBox.warning(self, "打开失败", str(exc))

    def _generate_daily(self):
        self._generate(reports_service.generate_daily_report, "日报")

    def _generate_weekly(self):
        self._generate(reports_service.generate_weekly_report, "周报")

    def _generate_monthly(self):
        self._generate(reports_service.generate_monthly_report, "月报")

    def _generate(self, generator, report_name: str) -> None:
        try:
            path = generator(self.db_path, self.reports_dir)
            self._sync_one(path)
            QMessageBox.information(self, "生成成功", f"{report_name}已保存\n{path}")
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self, "生成失败", str(exc))

    def _sync_selected(self) -> None:
        file_path = self._selected_path()
        if not file_path:
            return
        if not self.obsidian_path:
            QMessageBox.warning(self, "未配置", "请在设置页配置 Obsidian 输出路径。")
            return
        try:
            self._sync_one(file_path)
            QMessageBox.information(self, "同步完成", "选中的报告已同步到 Obsidian。")
        except Exception as exc:
            QMessageBox.warning(self, "同步失败", str(exc))

    def _sync_one(self, filepath):
        if self.obsidian_path and os.path.exists(filepath):
            reports_service.sync_report_to_obsidian(filepath, self.obsidian_path)
