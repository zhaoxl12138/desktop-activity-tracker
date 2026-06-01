"""Rule config page - edit software classification rules."""

import yaml

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QLineEdit, QTextEdit, QComboBox, QPushButton, QMessageBox, QFrame, QSplitter
)
from PySide6.QtCore import Qt

from ..style import (
    COLORS, SECTION_TITLE, BUTTON_PRIMARY_STYLE, BUTTON_SECONDARY_STYLE, INPUT_STYLE
)

LIST_STYLE = f"""
    QListWidget {{
        background: {COLORS['card_bg']};
        border: 1px solid {COLORS['border']};
        border-radius: 8px;
        font-size: 13px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 10px 14px;
        border-radius: 6px;
        margin: 1px 4px;
    }}
    QListWidget::item:selected {{
        background: {COLORS['primary']};
        color: white;
        font-weight: 600;
    }}
    QListWidget::item:hover:!selected {{
        background: {COLORS['bg']};
    }}
"""


class RuleConfigPage(QWidget):
    def __init__(self, config_path):
        super().__init__()
        self.config_path = config_path
        self._load_config()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        lbl = QLabel("规则配置")
        lbl.setStyleSheet(SECTION_TITLE)
        layout.addWidget(lbl)

        splitter = QSplitter(Qt.Horizontal)

        # Left: category list
        left = QFrame()
        left.setStyleSheet(
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 10px; padding: 4px;"
        )
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        cat_header = QLabel("分类列表")
        cat_header.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {COLORS['text_secondary']};"
            f"padding: 2px 4px;"
        )
        left_layout.addWidget(cat_header)

        self.cat_list = QListWidget()
        self.cat_list.setStyleSheet(LIST_STYLE)
        self.cat_list.currentRowChanged.connect(self._on_cat_selected)
        left_layout.addWidget(self.cat_list, 1)
        splitter.addWidget(left)

        # Right: editor
        right = QFrame()
        right.setStyleSheet(
            f"background: {COLORS['card_bg']}; border: 1px solid {COLORS['border']};"
            f"border-radius: 10px; padding: 4px;"
        )
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(10)

        section_label_style = f"font-size: 12px; font-weight: 700; color: {COLORS['text_secondary']};"

        lbl_name = QLabel("分类名称")
        lbl_name.setStyleSheet(section_label_style)
        right_layout.addWidget(lbl_name)
        self.edit_name = QLineEdit()
        self.edit_name.setStyleSheet(INPUT_STYLE)
        right_layout.addWidget(self.edit_name)

        lbl_procs = QLabel("进程名（每行一个）")
        lbl_procs.setStyleSheet(section_label_style)
        right_layout.addWidget(lbl_procs)
        self.edit_processes = QTextEdit()
        self.edit_processes.setMaximumHeight(120)
        self.edit_processes.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f"padding: 8px; font-size: 13px; background: {COLORS['card_bg']};"
            f"color: {COLORS['text']};"
        )
        right_layout.addWidget(self.edit_processes)

        lbl_kws = QLabel("标题关键词（每行一个）")
        lbl_kws.setStyleSheet(section_label_style)
        right_layout.addWidget(lbl_kws)
        self.edit_keywords = QTextEdit()
        self.edit_keywords.setMaximumHeight(120)
        self.edit_keywords.setStyleSheet(
            f"border: 1px solid {COLORS['border']}; border-radius: 6px;"
            f"padding: 8px; font-size: 13px; background: {COLORS['card_bg']};"
            f"color: {COLORS['text']};"
        )
        right_layout.addWidget(self.edit_keywords)

        lbl_rule = QLabel("计时规则")
        lbl_rule.setStyleSheet(section_label_style)
        right_layout.addWidget(lbl_rule)
        self.edit_rule = QComboBox()
        self.edit_rule.addItems(["interactive_required (需要活跃)", "passive_allowed (允许被动观看)"])
        self.edit_rule.setStyleSheet(f"""
            QComboBox {{
                border: 1px solid {COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                background: {COLORS['card_bg']};
                color: {COLORS['text']};
            }}
            QComboBox:hover {{ border-color: {COLORS['primary']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {COLORS['card_bg']};
                border: 1px solid {COLORS['border']};
                border-radius: 4px;
                selection-background-color: {COLORS['primary']};
                selection-color: white;
                padding: 4px;
            }}
        """)
        right_layout.addWidget(self.edit_rule)

        right_layout.addStretch()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        btn_save = QPushButton("保存修改")
        btn_save.setStyleSheet(BUTTON_PRIMARY_STYLE)
        btn_save.setCursor(Qt.PointingHandCursor)
        btn_save.clicked.connect(self._save_current)

        btn_add = QPushButton("添加分类")
        btn_add.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_add.setCursor(Qt.PointingHandCursor)
        btn_add.clicked.connect(self._add_category)

        btn_delete = QPushButton("删除分类")
        btn_delete.setStyleSheet(BUTTON_SECONDARY_STYLE)
        btn_delete.setCursor(Qt.PointingHandCursor)
        btn_delete.clicked.connect(self._delete_current)

        btn_row.addStretch()
        btn_row.addWidget(btn_add)
        btn_row.addWidget(btn_delete)
        btn_row.addWidget(btn_save)
        right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([200, 500])
        layout.addWidget(splitter, 1)

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
