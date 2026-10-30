"""Reports center - generate, select, open, download, and sync reports."""

from __future__ import annotations

import os
import time

from PySide6.QtCore import QItemSelectionModel, Qt, QTimer
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHeaderView,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...services import reports_service
from .. import style as ui_style


class ReportsPage(QWidget):
    def __init__(self, db_path, reports_dir, obsidian_path="", *, paths=None, background_tasks=None):
        super().__init__()
        self.db_path = db_path
        self.reports_dir = reports_dir
        from ...app_paths import AppPaths
        self.paths = paths or AppPaths.from_database(db_path, reports_dir=reports_dir)
        self.obsidian_path = obsidian_path
        self.selected_report: dict | None = None
        self.selected_reports: list[dict] = []
        self._is_active = False
        self._last_signature = None
        self._page_size = 50
        self._report_pages = {"daily": 1, "weekly": 1, "monthly": 1}
        self._page_results: dict[str, reports_service.ReportPage] = {}
        self._report_loaded_at: dict[str, float] = {}
        from ..background_task_queue import BackgroundTaskQueue
        self._owns_tasks = background_tasks is None
        self.background_tasks = background_tasks or BackgroundTaskQueue(self)
        self._generation_jobs = {}
        self.background_tasks.task_completed.connect(self._generation_completed)
        self.background_tasks.task_failed.connect(self._generation_failed)
        self._compact_preview = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(8)

        title = QLabel("报告中心")
        self.page_title = title
        title.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(title)
        from ...time_model import TIME_DEFINITION
        title.setToolTip(TIME_DEFINITION)

        subtitle = QLabel("生成、查看和导出你的时间报告。")
        self.subtitle = subtitle
        subtitle.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        layout.addWidget(subtitle)
        self.generation_bar = self._build_generation_bar()
        layout.addWidget(self.generation_bar)
        self.automation_status = QLabel()
        self.automation_status.setTextFormat(Qt.PlainText)
        self.automation_status.setWordWrap(True)
        self.automation_status.setStyleSheet(
            f"color: {ui_style.COLORS['text_secondary']}; font-size: 12px;")
        layout.addWidget(self.automation_status)

        self.compact_bar = QWidget()
        compact = QHBoxLayout(self.compact_bar)
        compact.setContentsMargins(0,0,0,0)
        self.btn_show_list = self._button('报告列表',lambda:self._show_compact(False))
        self.btn_show_preview = self._button('正文预览',lambda:self._show_compact(True))
        compact.addWidget(self.btn_show_list)
        compact.addWidget(self.btn_show_preview)
        compact.addStretch()
        layout.addWidget(self.compact_bar)
        self.splitter = QSplitter(Qt.Horizontal)
        self.list_panel = self._build_report_list()
        self.detail_panel = self._build_detail_panel()
        self.splitter.addWidget(self.list_panel)
        self.splitter.addWidget(self.detail_panel)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setStretchFactor(0,3)
        self.splitter.setStretchFactor(1,7)
        self.splitter.setSizes([320,740])
        layout.addWidget(self.splitter,1)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.setInterval(60000)
        # Hide the unused compact pane before the first layout negotiation;
        # otherwise both minimum-size hints can expand a narrow top-level UI.
        self._apply_responsive()

    def activate(self, force: bool = False) -> None:
        was_active=self._is_active
        self._is_active = True
        if not self.timer.isActive():
            self.timer.start()
        if force or self._last_signature is None:
            self.refresh()
        elif not was_active and self.selected_report:
            self.preview.load_report(self.selected_report['file_path'])

    def deactivate(self) -> None:
        self._is_active = False
        self.timer.stop()
        if hasattr(self, 'preview'):
            self.preview.suspend()

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
        row = QGridLayout(frame)
        row.setContentsMargins(8, 6, 8, 6)
        row.setSpacing(6)

        label = QLabel("生成报告")
        label.setStyleSheet(
            f"font-size: 13px; color: {ui_style.COLORS['text_secondary']}; font-weight: 700;"
        )
        row.addWidget(label,0,0)
        label.hide()

        self.btn_daily = self._button("今日日报", self._generate_daily, primary=True)
        self.btn_weekly = self._button("本周周报", self._generate_weekly, primary=True)
        self.btn_monthly = self._button("本月月报", self._generate_monthly, primary=True)
        row.addWidget(self.btn_daily,0,1)
        row.addWidget(self.btn_weekly,0,2)
        row.addWidget(self.btn_monthly,0,3)

        self.btn_open_dir = self._button("打开报告目录", self._open_reports_dir)
        row.addWidget(self.btn_open_dir,0,4)
        row.setColumnStretch(0,1)
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
        self.tabs.currentChanged.connect(self._on_tab_changed)
        layout.addWidget(self.tabs)

        pager = QHBoxLayout()
        pager.setSpacing(10)
        pager.addStretch()
        self.btn_previous_page = self._button("上一页", self._previous_page)
        self.page_status = QLabel("第 1 / 1 页 · 共 0 份")
        self.page_status.setAlignment(Qt.AlignCenter)
        self.page_status.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']};"
        )
        self.btn_next_page = self._button("下一页", self._next_page)
        pager.addWidget(self.btn_previous_page)
        pager.addWidget(self.page_status)
        pager.addWidget(self.btn_next_page)
        pager.addStretch()
        layout.addLayout(pager)
        return frame

    def _build_detail_panel(self) -> QFrame:
        from ..widgets.report_preview import ReportPreview
        frame = QFrame()
        frame.setObjectName("reportDetailCard")
        frame.setMinimumWidth(0)
        frame.setStyleSheet(ui_style.get_dashboard_card_style())
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10,8,10,8)
        layout.setSpacing(6)
        self.detail_title = QLabel("选择一份报告")
        self.detail_title.setTextFormat(Qt.PlainText)
        self.detail_title.setWordWrap(True)
        self.detail_title.setStyleSheet(f"font-size:18px;font-weight:800;color:{ui_style.COLORS['text']};")
        layout.addWidget(self.detail_title)
        self.detail_meta = QLabel("从左侧列表选择报告后，可以下载、打开或同步。")
        self.detail_meta.setTextFormat(Qt.PlainText)
        self.detail_meta.setWordWrap(True)
        self.detail_meta.setStyleSheet(f"font-size:12px;color:{ui_style.COLORS['text_secondary']};")
        layout.addWidget(self.detail_meta)
        self.preview = ReportPreview(self.reports_dir,self.db_path)
        layout.addWidget(self.preview,1)
        actions = QHBoxLayout()
        self.btn_download = self._button("下载 Markdown",self._download_selected,primary=True)
        self.btn_open = self._button("打开报告",self._open_selected)
        self.btn_sync_selected = self._button("同步到 Obsidian",self._sync_selected)
        for button in (self.btn_download,self.btn_open,self.btn_sync_selected):
            actions.addWidget(button)
        layout.addLayout(actions)
        self._set_action_enabled(False)
        return frame

    def _show_compact(self, preview):
        self._compact_preview = bool(preview)
        self._apply_responsive()

    def _apply_responsive(self):
        compact = self.width() < 1000
        self.page_title.setVisible(not compact or not self._compact_preview)
        self.subtitle.setVisible(not compact)
        self.generation_bar.setVisible(not compact or not self._compact_preview)
        self.automation_status.setVisible(not compact or not self._compact_preview)
        self.compact_bar.setVisible(compact)
        self.list_panel.setVisible(not compact or not self._compact_preview)
        self.detail_panel.setVisible(not compact or self._compact_preview)
        self.tab_daily.setColumnHidden(1,compact)
        self.tab_weekly.setColumnHidden(1,compact)
        self.tab_monthly.setColumnHidden(1,compact)

    def resizeEvent(self,event):
        super().resizeEvent(event)
        self._apply_responsive()

    def closeEvent(self,event):
        self.deactivate()
        self.preview.close()
        if self._owns_tasks:
            self.background_tasks.shutdown()
        super().closeEvent(event)

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
            QPushButton {{ padding: 6px 10px; font-size: 12px; border-radius: 8px; }}
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

    def refresh(self, force_subdir: str | None = None):
        from ...services.intelligence_report_schedule import schedule_status
        self.automation_status.setText(schedule_status(self.paths.intelligence_dir))
        table_specs = [
            (self.tab_daily, "daily", "日报"),
            (self.tab_weekly, "weekly", "周报"),
            (self.tab_monthly, "monthly", "月报"),
        ]
        subdir = force_subdir or self._current_subdir()
        index = ("daily", "weekly", "monthly").index(subdir)
        table, _subdir, _title = table_specs[index]
        result = reports_service.list_report_page(
            self.reports_dir,
            subdir,
            page=self._report_pages[subdir],
            page_size=self._page_size,
        )
        self._report_pages[subdir] = result.page
        self._page_results[subdir] = result
        self._report_loaded_at[subdir] = time.monotonic()
        rows = result.rows
        signature = (
            result.page,
            result.total_pages,
            result.total_count,
            tuple(
                (row.get("filename"), row.get("size_text"), row.get("modified_text"), row.get('modified_ns'), row.get('size_bytes'))
                for row in rows
            ),
        )
        for tab_index, (_table, tab_subdir, title) in enumerate(table_specs):
            count = (
                result.total_count
                if tab_subdir == subdir
                else reports_service.count_reports(self.reports_dir, tab_subdir)
            )
            self.tabs.setTabText(tab_index, f"{title}  {count}")
        if self._last_signature is None:
            self._last_signature = [None, None, None]
        if self._last_signature[index] != signature or subdir == force_subdir:
            selected_paths = self._selected_file_paths(table)
            table.blockSignals(True)
            table.clearSelection()
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
                if report.get("file_path") in selected_paths:
                    table.selectionModel().select(
                        table.model().index(row_index, 0),
                        QItemSelectionModel.Select | QItemSelectionModel.Rows,
                    )
            table.blockSignals(False)
            self._last_signature[index] = signature
            if table is self.tabs.currentWidget():
                self._select_from_table(table)
        self._update_pager()

    def _current_subdir(self) -> str:
        return ("daily", "weekly", "monthly")[self.tabs.currentIndex()]

    def _on_tab_changed(self, *_args) -> None:
        self._clear_selection()
        subdir = self._current_subdir()
        loaded_at = self._report_loaded_at.get(subdir)
        if loaded_at is None or time.monotonic() - loaded_at >= 60:
            self.refresh(force_subdir=subdir)
            return
        self._update_pager()

    def _previous_page(self) -> None:
        self._change_page(-1)

    def _next_page(self) -> None:
        self._change_page(1)

    def _change_page(self, delta: int) -> None:
        subdir = self._current_subdir()
        self._report_pages[subdir] += delta
        self._clear_selection()
        self.refresh(force_subdir=subdir)

    def _update_pager(self) -> None:
        result = self._page_results.get(self._current_subdir())
        if result is None:
            self.page_status.setText("第 1 / 1 页 · 共 0 份")
            self.btn_previous_page.setEnabled(False)
            self.btn_next_page.setEnabled(False)
            return
        self.page_status.setText(
            f"第 {result.page} / {result.total_pages} 页 · 共 {result.total_count} 份"
        )
        self.btn_previous_page.setEnabled(
            result.total_count > 0 and result.page > 1
        )
        self.btn_next_page.setEnabled(
            result.total_count > 0 and result.page < result.total_pages
        )

    @staticmethod
    def _selected_file_paths(table: QTableWidget) -> set[str]:
        paths = set()
        for index in table.selectionModel().selectedRows():
            item = table.item(index.row(), 0)
            report = item.data(Qt.UserRole) if item is not None else None
            if report and report.get("file_path"):
                paths.add(str(report["file_path"]))
        return paths

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
                " · ".join(
                    [
                        report['report_type'],
                        report['size_text'],
                        f"更新 {report['modified_text']}",
                    ]
                )
            )
            self.detail_meta.setToolTip(report['filename'])
            self.btn_download.setText("下载 Markdown")
            self._set_action_enabled(True, allow_single_actions=True)
            self.preview.load_report(report['file_path'])
            self._compact_preview = True
            self._apply_responsive()
            return

        self.selected_report = None
        self.preview.clear('已选择多份报告，可使用批量下载')
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
        self.preview.clear()
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
        from datetime import date
        key = f'report:manual:{self.db_path}:{report_name}:{date.today().isoformat()}'
        if key in self._generation_jobs:
            return
        db_path, reports_dir, obsidian = self.db_path, self.reports_dir, self.obsidian_path
        def generate():
            path = generator(db_path,reports_dir)
            reports_service.sync_report_to_obsidian(path,obsidian)
            return path
        self._generation_jobs[key] = report_name
        if not self.background_tasks.submit(key,generate):
            self._generation_jobs.pop(key,None)
            return
        self.automation_status.setText(f'{report_name}正在后台生成…')

    def _generation_completed(self,key,result):
        name = self._generation_jobs.pop(key,None)
        if name is None:
            return
        index = {'日报':0,'周报':1,'月报':2}[name]
        self.tabs.setCurrentIndex(index)
        self._report_pages[self._current_subdir()]=1
        self.refresh(force_subdir=self._current_subdir())
        table = self.tabs.currentWidget()
        for row in range(table.rowCount()):
            report = table.item(row,0).data(Qt.UserRole)
            if os.path.normcase(report['file_path']) == os.path.normcase(str(result)):
                table.selectRow(row)
                break
        self.automation_status.setText(f'{name}已生成，可在右侧预览；未增加 AI 请求')

    def _generation_failed(self,key,error):
        if self._generation_jobs.pop(key,None) is not None:
            self.automation_status.setText('生成失败，可重试：'+error)

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
