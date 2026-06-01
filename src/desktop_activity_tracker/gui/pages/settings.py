"""Settings page - general, paths, data management."""

import os
import shutil
import yaml
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox
)
from PySide6.QtCore import Qt

from ..style import BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE


class SettingsPage(QWidget):
    def __init__(self, config_path, db_path, reports_dir):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.reports_dir = reports_dir
        self._load_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        lbl = QLabel("设置")
        lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(lbl)

        # ── Basic settings ──
        g1 = QGroupBox("基础设置")
        g1.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; padding-top: 12px; }")
        g1l = QVBoxLayout(g1)
        g1l.setSpacing(10)

        self.chk_autostart = QCheckBox("开机自启动")
        self.chk_autostart.setStyleSheet("font-size: 13px;")
        g1l.addWidget(self.chk_autostart)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("采样间隔 (秒):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(1, 60)
        self.spin_interval.setValue(self.config.get("sample_interval_seconds", 5))
        h1.addWidget(self.spin_interval)
        h1.addStretch()
        g1l.addLayout(h1)

        h2 = QHBoxLayout()
        h2.addWidget(QLabel("空闲阈值 (秒):"))
        self.spin_idle = QSpinBox()
        self.spin_idle.setRange(10, 600)
        self.spin_idle.setValue(self.config.get("idle_threshold_seconds", 60))
        h2.addWidget(self.spin_idle)
        h2.addStretch()
        g1l.addLayout(h2)

        layout.addWidget(g1)

        # ── Path settings ──
        g2 = QGroupBox("路径设置")
        g2.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; padding-top: 12px; }")
        g2l = QVBoxLayout(g2)
        g2l.setSpacing(10)

        for label_text, default_val, attr in [
            ("数据库路径:", "data/usage.db", "edit_db"),
            ("日报输出路径:", "reports/daily/", "edit_reports"),
            ("Obsidian 输出路径:", "", "edit_obsidian"),
        ]:
            h = QHBoxLayout()
            h.addWidget(QLabel(label_text))
            edit = QLineEdit()
            edit.setStyleSheet("padding: 4px; font-size: 13px;")
            if attr == "edit_db":
                edit.setText(self.config.get("db_path", default_val))
            elif attr == "edit_reports":
                edit.setText(self.reports_dir)
            else:
                edit.setText(self.config.get("obsidian_output_path", default_val))
                edit.setPlaceholderText("例如: E:\\obsidian_github\\LifeOS\\TimeTracker")
            setattr(self, attr, edit)
            h.addWidget(edit)
            btn = QPushButton("...")
            btn.setFixedWidth(30)
            btn.clicked.connect(lambda checked, e=edit: self._browse_dir(e))
            h.addWidget(btn)
            g2l.addLayout(h)

        layout.addWidget(g2)

        # ── Data management ──
        g3 = QGroupBox("数据管理")
        g3.setStyleSheet("QGroupBox { font-size: 14px; font-weight: bold; padding-top: 12px; }")
        g3l = QVBoxLayout(g3)
        g3l.setSpacing(10)

        data_btns = QHBoxLayout()
        btn_backup = QPushButton("备份数据库")
        btn_backup.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_backup.clicked.connect(self._backup_db)
        btn_clean = QPushButton("清理30天前记录")
        btn_clean.setStyleSheet(BUTTON_SECONDARY_STYLE)
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
        btn_save.clicked.connect(self._save_all)
        layout.addWidget(btn_save, 0, Qt.AlignRight)

    def _load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _save_all(self):
        self.config["sample_interval_seconds"] = self.spin_interval.value()
        self.config["idle_threshold_seconds"] = self.spin_idle.value()
        self.config["db_path"] = self.edit_db.text().strip()
        self.config["obsidian_output_path"] = self.edit_obsidian.text().strip()
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)
        QMessageBox.information(self, "成功", "设置已保存。")

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
