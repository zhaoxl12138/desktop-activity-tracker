"""Rule config page - edit software classification rules."""

import os
import yaml

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QTextEdit, QComboBox, QPushButton, QMessageBox, QFrame, QSplitter
)
from PySide6.QtCore import Qt

from ..style import CARD_STYLE, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE


class RuleConfigPage(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self._load_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        lbl = QLabel("规则配置")
        lbl.setStyleSheet("font-size: 18px; font-weight: bold; color: #2C3E50;")
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Horizontal)

        # Left: category list
        left = QFrame()
        left.setStyleSheet(CARD_STYLE)
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("分类列表"))
        self.cat_list = QListWidget()
        self.cat_list.setStyleSheet("font-size: 14px;")
        self.cat_list.currentRowChanged.connect(self._on_cat_selected)
        left_layout.addWidget(self.cat_list)
        splitter.addWidget(left)

        # Right: editor
        right = QFrame()
        right.setStyleSheet(CARD_STYLE)
        right_layout = QVBoxLayout(right)
        right_layout.setSpacing(12)

        right_layout.addWidget(QLabel("分类名称"))
        self.edit_name = QLineEdit()
        self.edit_name.setStyleSheet("padding: 6px; font-size: 13px;")
        right_layout.addWidget(self.edit_name)

        right_layout.addWidget(QLabel("进程名（每行一个）"))
        self.edit_processes = QTextEdit()
        self.edit_processes.setMaximumHeight(120)
        self.edit_processes.setStyleSheet("font-size: 13px;")
        right_layout.addWidget(self.edit_processes)

        right_layout.addWidget(QLabel("标题关键词（每行一个）"))
        self.edit_keywords = QTextEdit()
        self.edit_keywords.setMaximumHeight(120)
        self.edit_keywords.setStyleSheet("font-size: 13px;")
        right_layout.addWidget(self.edit_keywords)

        right_layout.addWidget(QLabel("计时规则"))
        self.edit_rule = QComboBox()
        self.edit_rule.addItems(["interactive_required (需要活跃)", "passive_allowed (允许被动观看)"])
        right_layout.addWidget(self.edit_rule)

        right_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_save = QPushButton("保存修改")
        btn_save.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_save.clicked.connect(self._save_current)
        btn_add = QPushButton("添加分类")
        btn_add.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_add.clicked.connect(self._add_category)
        btn_delete = QPushButton("删除分类")
        btn_delete.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_delete.clicked.connect(self._delete_current)
        btn_row.addStretch()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_save)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter)

        self._populate_list()

    def _load_config(self):
        with open(self.config_path, "r", encoding="utf-8") as f:
            self.config = yaml.safe_load(f)

    def _save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.config, f, allow_unicode=True, default_flow_style=False)

    def _populate_list(self):
        self.cat_list.clear()
        for key, cat in self.config["categories"].items():
            item = QListWidgetItem(f"{cat['display_name']} ({key})")
            item.setData(Qt.UserRole, key)
            self.cat_list.addItem(item)

    def _on_cat_selected(self, row):
        if row < 0:
            return
        key = self.cat_list.item(row).data(Qt.UserRole)
        cat = self.config["categories"][key]
        self.edit_name.setText(cat.get("display_name", ""))
        proc_list = cat.get("match", {}).get("process_names", [])
        self.edit_processes.setPlainText("\n".join(proc_list))
        kw_list = cat.get("match", {}).get("title_keywords", [])
        self.edit_keywords.setPlainText("\n".join(kw_list))
        rule = cat.get("active_rule", "interactive_required")
        self.edit_rule.setCurrentIndex(0 if rule == "interactive_required" else 1)

    def _save_current(self):
        row = self.cat_list.currentRow()
        if row < 0:
            return
        key = self.cat_list.item(row).data(Qt.UserRole)
        cat = self.config["categories"][key]
        cat["display_name"] = self.edit_name.text().strip()
        cat["match"]["process_names"] = [p.strip() for p in self.edit_processes.toPlainText().split("\n") if p.strip()]
        cat["match"]["title_keywords"] = [k.strip() for k in self.edit_keywords.toPlainText().split("\n") if k.strip()]
        cat["active_rule"] = "interactive_required" if self.edit_rule.currentIndex() == 0 else "passive_allowed"
        self._save_config()
        self._populate_list()
        QMessageBox.information(self, "成功", f"分类 '{cat['display_name']}' 已保存")

    def _add_category(self):
        new_key = f"custom_{len(self.config['categories'])}"
        self.config["categories"][new_key] = {
            "display_name": "新分类",
            "active_rule": "interactive_required",
            "match": {"process_names": [], "title_keywords": []}
        }
        self._save_config()
        self._populate_list()
        self.cat_list.setCurrentRow(self.cat_list.count() - 1)

    def _delete_current(self):
        row = self.cat_list.currentRow()
        if row < 0:
            return
        key = self.cat_list.item(row).data(Qt.UserRole)
        if key in ("other",):
            QMessageBox.warning(self, "不可删除", "默认分类不可删除。")
            return
        reply = QMessageBox.question(self, "确认删除", f"确定删除分类 '{key}' 吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.config["categories"][key]
            self._save_config()
            self._populate_list()
