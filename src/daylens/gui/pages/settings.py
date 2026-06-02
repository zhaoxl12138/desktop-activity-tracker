"""Settings page - general configuration and data maintenance."""

import yaml
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QSpinBox,
    QPushButton, QCheckBox, QFileDialog, QMessageBox, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt

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
            setattr(self, attr, edit)
            h.addWidget(edit, 1)
            btn = QPushButton("...")
            btn.setFixedWidth(36)
            btn.setStyleSheet(build_browse_btn_style())
            btn.setCursor(Qt.PointingHandCursor)
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

    def _load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _save_all(self):
        sample_interval = self.spin_interval.value()
        idle_threshold = self.spin_idle.value()

        # Reload config to pick up any external changes
        self._load_config()

        # Write to both top-level and tracker sub-dict for compatibility
        self.config["sample_interval_seconds"] = sample_interval
        self.config["idle_threshold_seconds"] = idle_threshold
        self.config["db_path"] = self.edit_db.text().strip()
        self.config["obsidian_output_path"] = self.edit_obsidian.text().strip()

        tracker = self.config.setdefault("tracker", {})
        tracker["sample_interval_seconds"] = sample_interval
        tracker["idle_threshold_seconds"] = idle_threshold

        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

        # Hot-reload worker (settings + classifier)
        if self.worker:
            self.worker.update_settings(self.config)

        QMessageBox.information(self, "成功", "设置已保存，采样间隔和空闲阈值已实时生效。")

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "选择目录")
        if d:
            edit.setText(d)

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
