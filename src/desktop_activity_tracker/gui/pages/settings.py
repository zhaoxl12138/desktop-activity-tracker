"""Settings page - general, paths, data management."""

import os
import sys
import shutil
import winreg
import yaml
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt

from ..style import (
    COLORS, SECTION_TITLE, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE, INPUT_STYLE
)


GROUP_STYLE = f"""
    QGroupBox {{
        font-size: 14px;
        font-weight: 700;
        color: {COLORS['text']};
        border: 1px solid {COLORS['border']};
        border-radius: 14px;
        margin-top: 14px;
        background: {COLORS['card_bg']};
        padding: 24px 16px 16px 16px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 8px;
        color: {COLORS['text']};
    }}
"""

BROWSE_BTN_STYLE = f"""
    QPushButton {{
        background: {COLORS['panel_bg_alt']};
        color: {COLORS['text_secondary']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        font-size: 14px;
        font-weight: 700;
        padding: 4px 0;
    }}
    QPushButton:hover {{
        background: {COLORS['card_bg_alt']};
        border-color: {COLORS['primary']};
        color: {COLORS['primary']};
    }}
"""

AUTOSTART_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
AUTOSTART_NAME = "DesktopActivityTracker"


def _get_exe_path():
    """Get the exe path or script path for autostart."""
    if getattr(sys, 'frozen', False):
        return sys.executable
    return sys.executable


class SettingsPage(QWidget):
    def __init__(self, config_path, db_path, reports_dir, worker=None):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.reports_dir = reports_dir
        self.worker = worker
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
        lbl.setStyleSheet(SECTION_TITLE)
        layout.addWidget(lbl)

        # ── Basic settings ──
        g1 = QGroupBox("基础设置")
        g1.setStyleSheet(GROUP_STYLE)
        g1l = QVBoxLayout(g1)
        g1l.setContentsMargins(16, 20, 16, 16)
        g1l.setSpacing(12)

        self.chk_autostart = QCheckBox("开机自启动")
        self.chk_autostart.setChecked(self._is_autostart_enabled())
        g1l.addWidget(self.chk_autostart)

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

        # ── Path settings ──
        g2 = QGroupBox("路径设置")
        g2.setStyleSheet(GROUP_STYLE)
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
            setattr(self, attr, edit)
            h.addWidget(edit, 1)
            btn = QPushButton("...")
            btn.setFixedWidth(36)
            btn.setStyleSheet(BROWSE_BTN_STYLE)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked, e=edit: self._browse_dir(e))
            h.addWidget(btn)
            g2l.addLayout(h)

        layout.addWidget(g2)

        # ── Data management ──
        g3 = QGroupBox("数据管理")
        g3.setStyleSheet(GROUP_STYLE)
        g3l = QVBoxLayout(g3)
        g3l.setContentsMargins(16, 20, 16, 16)
        g3l.setSpacing(10)

        data_btns = QHBoxLayout()
        data_btns.setSpacing(10)

        btn_backup = QPushButton("备份数据库")
        btn_backup.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_backup.setCursor(Qt.PointingHandCursor)
        btn_backup.clicked.connect(self._backup_db)

        btn_clean = QPushButton("清理30天前记录")
        btn_clean.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_clean.setCursor(Qt.PointingHandCursor)
        btn_clean.clicked.connect(self._clean_old)

        data_btns.addWidget(btn_backup)
        data_btns.addWidget(btn_clean)
        data_btns.addStretch()
        g3l.addLayout(data_btns)

        layout.addWidget(g3)

        # ── Save ──
        layout.addStretch()
        btn_save = QPushButton("保存设置")
        btn_save.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_all)
        layout.addWidget(btn_save, 0, Qt.AlignRight)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    def _load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _is_autostart_enabled(self):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                                0, winreg.KEY_READ) as key:
                winreg.QueryValueEx(key, AUTOSTART_NAME)
                return True
        except FileNotFoundError:
            return False

    def _set_autostart(self, enable):
        exe_path = _get_exe_path()
        try:
            if enable:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                                    0, winreg.KEY_SET_VALUE) as key:
                    winreg.SetValueEx(key, AUTOSTART_NAME, 0, winreg.REG_SZ,
                                      f'"{exe_path}"')
            else:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, AUTOSTART_KEY,
                                    0, winreg.KEY_SET_VALUE) as key:
                    winreg.DeleteValue(key, AUTOSTART_NAME)
        except (FileNotFoundError, OSError):
            pass

    def _save_all(self):
        sample_interval = self.spin_interval.value()
        idle_threshold = self.spin_idle.value()

        # Write to both top-level and tracker sub-dict for compatibility
        self.config["sample_interval_seconds"] = sample_interval
        self.config["idle_threshold_seconds"] = idle_threshold
        self.config["db_path"] = self.edit_db.text().strip()
        self.config["reports_dir"] = self.edit_reports.text().strip()
        self.config["obsidian_output_path"] = self.edit_obsidian.text().strip()

        tracker = self.config.setdefault("tracker", {})
        tracker["sample_interval_seconds"] = sample_interval
        tracker["idle_threshold_seconds"] = idle_threshold

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)

        # Hot-reload worker settings
        if self.worker:
            self.worker.update_settings(self.config)

        # Autostart
        self._set_autostart(self.chk_autostart.isChecked())

        QMessageBox.information(self, "成功", "设置已保存。\n采样间隔和空闲阈值已实时生效。")

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            edit.setText(d)

    def _backup_db(self):
        if not os.path.exists(self.db_path):
            QMessageBox.warning(self, "无数据库", "数据库文件不存在。")
            return
        dest, _ = QFileDialog.getSaveFileName(
            self, "备份数据库",
            f"usage_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
            "DB Files (*.db)"
        )
        if dest:
            shutil.copy2(self.db_path, dest)
            QMessageBox.information(self, "成功", f"数据库已备份到\n{dest}")

    def _clean_old(self):
        reply = QMessageBox.question(
            self, "确认清理", "将删除 30 天前的采样记录，汇总数据不受影响。\n确定继续？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return
        import sqlite3
        from datetime import timedelta
        cutoff = (datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                  - timedelta(days=30)).strftime("%Y-%m-%d")
        conn = sqlite3.connect(self.db_path)
        conn.execute("DELETE FROM activity_logs WHERE date < ?", (cutoff,))
        conn.commit()
        conn.close()
        QMessageBox.information(self, "完成", f"已清理 {cutoff} 之前的记录。")
