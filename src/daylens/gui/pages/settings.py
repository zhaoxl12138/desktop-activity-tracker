"""Settings page - general configuration and data maintenance."""

import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal

from ...services import settings_service
from ...services.data_quality_service import (
    inspect_data_quality,
    preview_repairable_sessions,
    repair_legacy_session_data,
)
from ...services.restart_service import database_path_changed
from ...utils import fmt_seconds
from .. import style as ui_style


def build_group_style() -> str:
    return f"""
    QGroupBox {{
        font-size: 14px;
        font-weight: 700;
        color: {ui_style.COLORS['text']};
        border: 1px solid {ui_style.COLORS['border']};
        border-radius: 14px;
        margin-top: 14px;
        background: {ui_style.COLORS['card_bg']};
        padding: 24px 16px 16px 16px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
        color: {ui_style.COLORS['text']};
    }}
"""

def build_browse_btn_style() -> str:
    return f"""
    QPushButton {{
        background: {ui_style.COLORS['panel_bg_alt']};
        color: {ui_style.COLORS['text_secondary']};
        border: 1px solid {ui_style.COLORS['border']};
        border-radius: 8px;
        font-size: 14px;
        font-weight: 700;
        padding: 4px 0;
    }}
    QPushButton:hover {{
        background: {ui_style.COLORS['card_bg_alt']};
        border-color: {ui_style.COLORS['primary']};
        color: {ui_style.COLORS['primary']};
    }}
"""

class SettingsPage(QWidget):
    restart_requested = Signal()
    config_saved = Signal(dict)

    def __init__(self, config_path, db_path, reports_dir, worker=None, background_tasks=None):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.worker = worker
        self.background_tasks = background_tasks
        self._quality_inspect_key = "settings:quality-inspect"
        self._quality_repair_key = "settings:quality-repair"
        self._load_config()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        layout = QVBoxLayout(content)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(16)

        lbl = QLabel("设置")
        lbl.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(lbl)

        # ── Basic settings ──
        g1 = QGroupBox("基础设置")
        g1.setStyleSheet(build_group_style())
        g1l = QVBoxLayout(g1)
        g1l.setContentsMargins(16, 20, 16, 16)
        g1l.setSpacing(12)

        basic_hint = QLabel("调整采样频率、空闲判定和数据输出路径。")
        basic_hint.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        g1l.addWidget(basic_hint)

        h1 = QHBoxLayout()
        h1.setSpacing(10)
        h1.addWidget(QLabel("采样间隔 (秒):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        tracker_cfg = self.config.get("tracker", {})
        self.spin_interval.setValue(tracker_cfg.get("sample_interval_seconds",
            self.config.get("sample_interval_seconds", 1)))
        h1.addWidget(self.spin_interval)
        h1.addStretch()
        g1l.addLayout(h1)

        h2 = QHBoxLayout()
        h2.setSpacing(10)
        h2.addWidget(QLabel("空闲阈值 (秒):"))
        self.spin_idle = QSpinBox()
        self.spin_idle.setRange(10, 600)
        self.spin_idle.setValue(tracker_cfg.get("idle_threshold_seconds",
            self.config.get("idle_threshold_seconds", 60)))
        h2.addWidget(self.spin_idle)
        h2.addStretch()
        g1l.addLayout(h2)

        layout.addWidget(g1)

        # ── Startup ──
        g_startup = QGroupBox("开机自启")
        g_startup.setStyleSheet(build_group_style())
        gsl = QVBoxLayout(g_startup)
        gsl.setContentsMargins(16, 20, 16, 16)
        gsl.setSpacing(8)

        startup_hint = QLabel("启用后 DayLens 将随系统自动启动并最小化到托盘。")
        startup_hint.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        gsl.addWidget(startup_hint)

        self.chk_startup = QCheckBox("开机自启")
        self.chk_startup.setChecked(self.config.get("startup_enabled", False))
        self.chk_startup.setStyleSheet(
            f"font-size: 14px; font-weight: 700; color: {ui_style.COLORS['text']};"
            f" QCheckBox::indicator {{ width: 18px; height: 18px; }}"
        )
        gsl.addWidget(self.chk_startup)
        layout.addWidget(g_startup)

        # ── Path settings ──
        g2 = QGroupBox("路径设置")
        g2.setStyleSheet(build_group_style())
        g2l = QVBoxLayout(g2)
        g2l.setContentsMargins(16, 20, 16, 16)
        g2l.setSpacing(10)

        for label_text, default_val, attr, get_val in [
            ("数据库路径:", "usage.db", "edit_db", self.config.get("db_path", "usage.db")),
            ("日报输出路径:", "reports", "edit_reports", self.reports_dir),
            ("Obsidian 输出路径:", "", "edit_obsidian", self.config.get("obsidian_output_path", "")),
        ]:
            h = QHBoxLayout()
            h.setSpacing(8)
            lbl = QLabel(label_text)
            lbl.setFixedWidth(120)
            h.addWidget(lbl)
            edit = QLineEdit()
            edit.setText(get_val)
            if attr == "edit_obsidian":
                edit.setPlaceholderText("例如: E:\\obsidian_github\\LifeOS\\TimeTracker")
            elif attr == "edit_reports":
                edit.setReadOnly(True)
                edit.setToolTip("报告目录随数据库路径自动确定")
            setattr(self, attr, edit)
            h.addWidget(edit, 1)
            if attr != "edit_reports":
                btn = QPushButton("...")
                btn.setFixedWidth(36)
                btn.setStyleSheet(build_browse_btn_style())
                btn.setCursor(Qt.PointingHandCursor)
                if attr == "edit_db":
                    btn.clicked.connect(self._browse_database)
                else:
                    btn.clicked.connect(lambda checked, e=edit: self._browse_dir(e))
                h.addWidget(btn)
            g2l.addLayout(h)

        layout.addWidget(g2)

        # ── Data management ──
        g3 = QGroupBox("数据维护")
        g3.setStyleSheet(build_group_style())
        g3l = QVBoxLayout(g3)
        g3l.setContentsMargins(16, 20, 16, 16)
        g3l.setSpacing(10)

        data_hint = QLabel("可按需清理 30 天前的采样记录，汇总统计不受影响。")
        data_hint.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        g3l.addWidget(data_hint)

        btn_clean = QPushButton("清理30天前记录")
        btn_clean.setStyleSheet(ui_style.get_button_secondary_style())
        btn_clean.setCursor(Qt.PointingHandCursor)
        btn_clean.clicked.connect(self._clean_old)
        g3l.addWidget(btn_clean, 0, Qt.AlignLeft)

        self.btn_quality = QPushButton("预览并修复数据")
        self.btn_quality.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_quality.setCursor(Qt.PointingHandCursor)
        self.btn_quality.clicked.connect(self._check_data_quality)
        g3l.addWidget(self.btn_quality, 0, Qt.AlignLeft)

        layout.addWidget(g3)

        # ── Save ──
        layout.addStretch()
        btn_save = QPushButton("保存设置")
        btn_save.setStyleSheet(ui_style.get_button_primary_style())
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_all)
        layout.addWidget(btn_save, 0, Qt.AlignRight)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        if self.background_tasks is not None:
            completed = getattr(self.background_tasks, "task_completed", None)
            failed = getattr(self.background_tasks, "task_failed", None)
            if completed is not None:
                completed.connect(self._on_background_task_completed)
            if failed is not None:
                failed.connect(self._on_background_task_failed)

    def _load_config(self):
        try:
            self.config = settings_service.load_page_config(self.config_path, self.db_path)
        except Exception as e:
            print(f"[SettingsPage] config load error: {e}")
            self.config = {}

    def _save_all(self):
        sample_interval = self.spin_interval.value()
        idle_threshold = self.spin_idle.value()
        try:
            requested_db_path = settings_service.normalize_database_path(self.edit_db.text())
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return
        requires_restart = database_path_changed(self.db_path, requested_db_path)

        # Reload config to pick up any external changes
        self._load_config()

        try:
            startup_enabled = self._toggle_startup(self.chk_startup.isChecked())
            self.chk_startup.setChecked(startup_enabled)
            self.config = settings_service.save_page_config(
                config_path=self.config_path,
                db_path=self.db_path,
                config=self.config,
                sample_interval=sample_interval,
                idle_threshold=idle_threshold,
                startup_enabled=startup_enabled,
                new_db_path=requested_db_path,
                obsidian_output_path=self.edit_obsidian.text().strip(),
            )
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", str(exc))
            return

        self.config_saved.emit(self.config)

        if requires_restart:
            QMessageBox.information(
                self,
                "设置已保存",
                "数据库路径已更改，DayLens 将自动重启以切换到新数据库。",
            )
            self.restart_requested.emit()
            return

        # Hot-reload worker (settings + classifier)
        if self.worker:
            self.worker.update_settings(self.config)

        QMessageBox.information(self, "成功", "设置已保存，采样间隔和空闲阈值已实时生效。")

    @staticmethod
    def _get_startup_link_path() -> str:
        return settings_service.get_startup_link_path()

    @staticmethod
    def _get_exe_path() -> str:
        import sys
        if getattr(sys, "frozen", False):
            return sys.executable
        return settings_service.get_release_exe_path()

    def _toggle_startup(self, enable: bool) -> bool:
        link_path = self._get_startup_link_path()
        if enable:
            exe_path = self._get_exe_path()
            if not os.path.isfile(exe_path):
                QMessageBox.warning(self, "提示",
                    f"未找到 DayLens.exe，请先打包程序。\n\n预期路径: {exe_path}")
                self.chk_startup.setChecked(False)
                return False
            try:
                settings_service.toggle_startup_shortcut(True, exe_path, link_path)
                return True
            except Exception as e:
                print(f"[SettingsPage] shortcut creation error: {e}")
                QMessageBox.warning(self, "失败", f"创建开机启动快捷方式失败:\n{e}")
                self.chk_startup.setChecked(False)
                return False
        else:
            settings_service.toggle_startup_shortcut(False, "", link_path)
            return False

    def _browse_database(self) -> None:
        selected, _ = QFileDialog.getSaveFileName(
            self,
            "选择数据库文件",
            self.edit_db.text().strip(),
            "SQLite 数据库 (*.db);;所有文件 (*)",
        )
        if selected:
            if not os.path.splitext(selected)[1]:
                selected += ".db"
            self.edit_db.setText(selected)

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            edit.setText(d)

    def _check_data_quality(self):
        tracker_config = self.config.get("tracker", {})
        sample_interval = tracker_config.get(
            "sample_interval_seconds",
            self.config.get("sample_interval_seconds", 1),
        )
        db_path = self.db_path
        def inspect_task() -> dict:
            return {
                "result": inspect_data_quality(
                    db_path,
                    sample_interval_seconds=sample_interval,
                ),
                "preview": preview_repairable_sessions(db_path),
            }

        if self.background_tasks is not None:
            if not self.background_tasks.submit(self._quality_inspect_key, inspect_task):
                return
            self.btn_quality.setEnabled(False)
            self.btn_quality.setText("检查中…")
            return
        try:
            self._show_quality_result(inspect_task(), sample_interval)
        except Exception as exc:
            QMessageBox.warning(self, "检查失败", str(exc))

    def _show_quality_result(self, payload: dict, sample_interval: int) -> None:
        result = payload["result"]
        preview = payload["preview"]
        repairable_count = int(preview["repairable_count"])
        if repairable_count:
            other_issues = max(0, int(result["issue_count"]) - repairable_count)
            dates = "、".join(preview["dates"])
            reply = QMessageBox.question(
                self,
                "数据修复预览",
                f"发现 {repairable_count} 条可安全修复的旧版娱乐挂机记录。\n"
                f"涉及日期：{dates}\n"
                f"重复空闲时间：{fmt_seconds(int(preview['duplicate_idle_seconds']))}\n"
                f"其他异常：{other_issues} 条\n\n"
                "修复前会自动备份数据库，是否继续？",
                QMessageBox.Yes | QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            def repair_task() -> dict:
                repaired = repair_legacy_session_data(
                    db_path,
                    reason="manual",
                )
                return {
                    "repaired": repaired,
                    "after": inspect_data_quality(
                        db_path,
                        sample_interval_seconds=sample_interval,
                    ),
                }

            if self.background_tasks is not None:
                if self.background_tasks.submit(self._quality_repair_key, repair_task):
                    self.btn_quality.setEnabled(False)
                    self.btn_quality.setText("修复中…")
                return
            self._show_quality_repair_result(repair_task())
            return
        if result["issue_count"]:
            QMessageBox.warning(
                self, "数据质量检查",
                f"检查 {result['checked_sessions']} 个 Session，发现 {result['issue_count']} 个问题。\n"
                f"当前可信度：{result['score']}%",
            )
            return
        QMessageBox.information(
            self, "数据质量检查",
            f"检查 {result['checked_sessions']} 个 Session，未发现异常。\n当前可信度：100%",
        )

    def _show_quality_repair_result(self, payload: dict) -> None:
        repaired = payload["repaired"]
        after = payload["after"]
        QMessageBox.information(
            self,
            "数据修复完成",
            f"已修复 {repaired['repaired_count']} 条记录。\n"
            f"剩余异常：{after['issue_count']} 条\n"
            f"备份文件：{repaired['backup_path']}",
        )

    def _on_background_task_completed(self, key: str, result: object) -> None:
        if key == self._quality_inspect_key:
            self.btn_quality.setEnabled(True)
            self.btn_quality.setText("预览并修复数据")
            if isinstance(result, dict):
                try:
                    tracker_config = self.config.get("tracker", {})
                    sample_interval = tracker_config.get(
                        "sample_interval_seconds",
                        self.config.get("sample_interval_seconds", 1),
                    )
                    self._show_quality_result(result, sample_interval)
                except Exception as exc:
                    QMessageBox.warning(self, "检查失败", str(exc))
            return
        if key == self._quality_repair_key:
            self.btn_quality.setEnabled(True)
            self.btn_quality.setText("预览并修复数据")
            if isinstance(result, dict):
                try:
                    self._show_quality_repair_result(result)
                except Exception as exc:
                    QMessageBox.warning(self, "修复失败", str(exc))

    def _on_background_task_failed(self, key: str, error: str) -> None:
        if key not in {self._quality_inspect_key, self._quality_repair_key}:
            return
        self.btn_quality.setEnabled(True)
        self.btn_quality.setText("预览并修复数据")
        QMessageBox.warning(self, "数据质量任务失败", error)

    def _clean_old(self):
        reply = QMessageBox.question(
            self, "确认清理", "将删除 30 天前的采样记录，汇总数据不受影响。\n确定继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        cutoff = settings_service.cleanup_old_logs(self.db_path, days=30)
        QMessageBox.information(self, "完成", f"已清理 {cutoff} 之前的记录。")
