"""Rule management page - edit category matching and timing strategy."""

from __future__ import annotations

import copy

import yaml
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox, QInputDialog,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ...app_scanner import classify_scanned_apps, scan_installed_apps
from ...classifier import Classifier
from ...services.rules_service import load_rule_categories, save_rule_categories
from .. import style as ui_style

_RULE_OPTIONS = [
    {
        "key": "interactive_required",
        "title": "主动交互型",
    },
    {
        "key": "passive_allowed",
        "title": "被动消费型",
    },
]
_RULE_INDEX = {item["key"]: index for index, item in enumerate(_RULE_OPTIONS)}


def build_list_style() -> str:
    return f"""
    QListWidget {{
        background: {ui_style.COLORS['panel_bg']};
        border: 1px solid {ui_style.COLORS['border']};
        border-radius: 10px;
        font-size: 13px;
        padding: 4px;
        outline: none;
    }}
    QListWidget::item {{
        padding: 12px 14px;
        border-radius: 6px;
        margin: 1px 4px;
    }}
    QListWidget::item:selected {{
        background: {ui_style.COLORS['primary']};
        color: white;
        font-weight: 600;
    }}
    QListWidget::item:hover:!selected {{
        background: {ui_style.COLORS['panel_bg_alt']};
    }}
"""


def _frame_style(
    object_name: str,
    background_key: str = "panel_bg",
    radius: int = 12,
    padding: int | None = None,
) -> str:
    padding_rule = f"padding: {padding}px;" if padding is not None else ""
    return f"""
    QFrame#{object_name} {{
        background: {ui_style.COLORS[background_key]};
        border: 1px solid {ui_style.COLORS['border']};
        border-radius: {radius}px;
        {padding_rule}
    }}
    """


def _section_card(title: str, desc: str = "") -> tuple[QFrame, QVBoxLayout]:
    frame = QFrame()
    frame.setObjectName("ruleSectionCard")
    frame.setStyleSheet(_frame_style("ruleSectionCard"))
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 14, 14, 14)
    layout.setSpacing(8)

    header = QLabel(title)
    header.setStyleSheet(
        f"font-size: 14px; font-weight: 700; color: {ui_style.COLORS['text']};"
    )
    layout.addWidget(header)

    if desc:
        hint = QLabel(desc)
        hint.setWordWrap(True)
        hint.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        layout.addWidget(hint)

    return frame, layout


class RuleConfigPage(QWidget):
    def __init__(self, config_path, db_path, worker=None):
        super().__init__()
        self.config_path = config_path
        self.db_path = db_path
        self.worker = worker
        try:
            with open(self.config_path, "r", encoding="utf-8") as handle:
                factory_config = yaml.safe_load(handle) or {}
        except (OSError, yaml.YAMLError):
            factory_config = {}
        self._factory_keys = set(factory_config.get("categories", {}))
        self.categories = load_rule_categories(self.config_path, self.db_path)
        self._loading_editor = False
        self._changing_selection = False
        self._current_key: str | None = None
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(14)

        title = QLabel("规则管理")
        title.setStyleSheet(ui_style.get_section_title())
        layout.addWidget(title)

        hint = QLabel("管理分类规则与计时策略。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"font-size: 12px; color: {ui_style.COLORS['text_muted']};")
        layout.addWidget(hint)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = self._build_category_panel()
        right = self._build_editor_panel()

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([300, 920])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)

        self.edit_name.textChanged.connect(self._mark_dirty)
        self.edit_rule.currentIndexChanged.connect(self._mark_dirty)
        self.edit_processes.textChanged.connect(self._mark_dirty)
        self.edit_keywords.textChanged.connect(self._mark_dirty)
        self._set_dirty(False)
        self._populate_list()
        if self.cat_list.count() > 0:
            self.cat_list.setCurrentRow(0)

    def _build_category_panel(self) -> QFrame:
        left = QFrame()
        self.category_panel = left
        left.setObjectName("ruleCategoryPanel")
        left.setStyleSheet(_frame_style("ruleCategoryPanel", "card_bg", 14, 4))
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(12, 12, 12, 12)
        left_layout.setSpacing(8)

        self.cat_header = QLabel("分类列表")
        self.cat_header.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {ui_style.COLORS['text_secondary']};"
            "padding: 2px 4px;"
        )
        left_layout.addWidget(self.cat_header)

        self.cat_summary = QLabel("选择分类后可编辑规则。")
        self.cat_summary.setWordWrap(True)
        self.cat_summary.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']}; padding: 0 4px 6px 4px;"
        )
        left_layout.addWidget(self.cat_summary)

        self.cat_meta = QLabel("")
        self.cat_meta.setWordWrap(True)
        self.cat_meta.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_secondary']}; padding: 0 4px 8px 4px;"
        )
        left_layout.addWidget(self.cat_meta)

        self.cat_list = QListWidget()
        self.cat_list.setStyleSheet(build_list_style())
        self.cat_list.currentRowChanged.connect(self._on_cat_selected)
        left_layout.addWidget(self.cat_list, 1)
        return left

    def _build_editor_panel(self) -> QFrame:
        right = QFrame()
        self.editor_panel = right
        right.setObjectName("ruleEditorPanel")
        right.setStyleSheet(_frame_style("ruleEditorPanel", "card_bg", 14, 4))
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        section_label_style = (
            f"font-size: 12px; font-weight: 700; color: {ui_style.COLORS['text_secondary']};"
        )

        top_row = QHBoxLayout()
        top_row.setSpacing(12)

        self.basic_card, basic_layout = _section_card("分类信息")
        lbl_name = QLabel("分类名称")
        lbl_name.setStyleSheet(section_label_style)
        basic_layout.addWidget(lbl_name)

        self.edit_name = QLineEdit()
        self.edit_name.setStyleSheet(ui_style.get_input_style())
        basic_layout.addWidget(self.edit_name)

        self.category_chip = QLabel("")
        self.category_chip.setStyleSheet(
            f"font-size: 12px; font-weight: 700; color: {ui_style.COLORS['text_secondary']};"
            f"background: {ui_style.COLORS['panel_bg_alt']}; border: 1px solid {ui_style.COLORS['border_light']};"
            "border-radius: 10px; padding: 5px 10px;"
        )
        basic_layout.addWidget(self.category_chip)
        top_row.addWidget(self.basic_card, 1)

        self.strategy_card, strategy_layout = _section_card("计时策略")
        lbl_rule = QLabel("策略类型")
        lbl_rule.setStyleSheet(section_label_style)
        strategy_layout.addWidget(lbl_rule)

        self.edit_rule = QComboBox()
        self.edit_rule.addItems([item["title"] for item in _RULE_OPTIONS])
        self.edit_rule.setStyleSheet(
            f"""
            QComboBox {{
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                background: {ui_style.COLORS['panel_bg_alt']};
                color: {ui_style.COLORS['text']};
            }}
            QComboBox:hover {{ border-color: {ui_style.COLORS['primary']}; }}
            QComboBox::drop-down {{ border: none; width: 24px; }}
            QComboBox QAbstractItemView {{
                background: {ui_style.COLORS['panel_bg_alt']};
                border: 1px solid {ui_style.COLORS['border']};
                border-radius: 4px;
                selection-background-color: {ui_style.COLORS['primary']};
                selection-color: white;
                padding: 4px;
            }}
            """
        )
        strategy_layout.addWidget(self.edit_rule)
        strategy_layout.addStretch()
        top_row.addWidget(self.strategy_card, 1)
        right_layout.addLayout(top_row)

        self.match_card, match_layout = _section_card(
            "识别规则",
            "进程名用于稳定识别，标题关键词用于浏览器和内容场景。",
        )
        self.match_card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.match_hint_frame = QFrame()
        self.match_hint_frame.setObjectName("ruleMatchHint")
        self.match_hint_frame.setMinimumHeight(48)
        self.match_hint_frame.setStyleSheet(
            _frame_style("ruleMatchHint", "card_bg_alt", 10)
        )
        match_hint_layout = QHBoxLayout(self.match_hint_frame)
        match_hint_layout.setContentsMargins(12, 7, 12, 7)
        match_hint_layout.setSpacing(8)

        hint_icon = QLabel("i")
        hint_icon.setAlignment(Qt.AlignCenter)
        hint_icon.setFixedSize(24, 24)
        hint_icon.setStyleSheet(
            f"font-size: 13px; font-weight: 700; color: {ui_style.COLORS['primary']};"
            f"background: {ui_style.COLORS['panel_bg_alt']}; border-radius: 12px;"
        )
        match_hint_layout.addWidget(hint_icon, 0, Qt.AlignTop)

        self.match_hint = QLabel("")
        self.match_hint.setWordWrap(True)
        self.match_hint.setAlignment(Qt.AlignVCenter | Qt.AlignLeft)
        self.match_hint.setStyleSheet(
            f"font-size: 12px; color: {ui_style.COLORS['text_muted']};"
        )
        match_hint_layout.addWidget(self.match_hint, 1)
        match_layout.addWidget(self.match_hint_frame)

        editors_row = QHBoxLayout()
        editors_row.setSpacing(12)

        proc_col = QVBoxLayout()
        proc_col.setSpacing(6)
        lbl_procs = QLabel("进程名（每行一个）")
        lbl_procs.setStyleSheet(section_label_style)
        proc_col.addWidget(lbl_procs)

        self.edit_processes = QTextEdit()
        self.edit_processes.setMinimumHeight(180)
        self.edit_processes.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.edit_processes.setStyleSheet(
            f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 8px;"
            f"padding: 8px; font-size: 13px; background: {ui_style.COLORS['panel_bg_alt']};"
            f"color: {ui_style.COLORS['text']};"
        )
        proc_col.addWidget(self.edit_processes)

        kw_col = QVBoxLayout()
        kw_col.setSpacing(6)
        lbl_kws = QLabel("标题关键词（每行一个）")
        lbl_kws.setStyleSheet(section_label_style)
        kw_col.addWidget(lbl_kws)

        self.edit_keywords = QTextEdit()
        self.edit_keywords.setMinimumHeight(180)
        self.edit_keywords.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.edit_keywords.setStyleSheet(
            f"border: 1px solid {ui_style.COLORS['border']}; border-radius: 8px;"
            f"padding: 8px; font-size: 13px; background: {ui_style.COLORS['panel_bg_alt']};"
            f"color: {ui_style.COLORS['text']};"
        )
        kw_col.addWidget(self.edit_keywords)

        editors_row.addLayout(proc_col, 1)
        editors_row.addLayout(kw_col, 1)
        match_layout.addLayout(editors_row)

        right_layout.addWidget(self.match_card, 1)

        self.action_bar = QFrame()
        self.action_bar.setObjectName("ruleActionBar")
        self.action_bar.setStyleSheet(
            "QFrame#ruleActionBar { background: transparent; border: none; }"
        )
        btn_row = QHBoxLayout(self.action_bar)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(10)

        self.btn_save = QPushButton("保存修改")
        self.btn_save.setStyleSheet(ui_style.get_button_primary_style())
        self.btn_save.setCursor(Qt.PointingHandCursor)
        self.btn_save.clicked.connect(self._save_current)

        self.btn_add = QPushButton("添加分类")
        self.btn_add.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_add.setCursor(Qt.PointingHandCursor)
        self.btn_add.clicked.connect(self._add_category)

        self.btn_delete = QPushButton("删除分类")
        self.btn_delete.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_delete.setCursor(Qt.PointingHandCursor)
        self.btn_delete.clicked.connect(self._delete_current)

        self.btn_rescan = QPushButton("重新扫描应用")
        self.btn_rescan.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_rescan.setCursor(Qt.PointingHandCursor)
        self.btn_rescan.clicked.connect(self._rescan_apps)

        self.btn_debug = QPushButton("测试分类")
        self.btn_debug.setStyleSheet(ui_style.get_button_secondary_style())
        self.btn_debug.setCursor(Qt.PointingHandCursor)
        self.btn_debug.clicked.connect(self._debug_classification)

        btn_row.addStretch()
        btn_row.addWidget(self.btn_add)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_rescan)
        btn_row.addWidget(self.btn_debug)
        btn_row.addWidget(self.btn_save)
        right_layout.addWidget(self.action_bar)
        return right

    def _save_to_db(self, candidate: dict[str, dict]) -> bool:
        try:
            save_rule_categories(self.db_path, candidate)
            return True
        except Exception as exc:
            QMessageBox.warning(self, "保存失败", f"规则未保存：{exc}")
            return False

    def _populate_list(self):
        was_blocked = self.cat_list.blockSignals(True)
        try:
            self.cat_list.clear()
            for key, cat in self.categories.items():
                prefix = "🔒" if key in self._factory_keys else "•"
                item = QListWidgetItem(f"{prefix} {cat['display_name']} · {key}")
                item.setData(Qt.UserRole, key)
                self.cat_list.addItem(item)
        finally:
            self.cat_list.blockSignals(was_blocked)
        self.cat_header.setText(f"分类列表（{self.cat_list.count()}）")

    def _on_cat_selected(self, row):
        if row < 0 or self._changing_selection:
            return

        key = self.cat_list.item(row).data(Qt.UserRole)
        if (
            self._current_key
            and key != self._current_key
            and not self._resolve_dirty_edits()
        ):
            self._select_key(self._current_key)
            return

        self._select_key(key)
        self._load_category(key)

    def _resolve_dirty_edits(self) -> bool:
        """Resolve pending editor changes before any state-changing action."""
        if not self._dirty:
            return True
        reply = QMessageBox.question(
            self,
            "未保存的修改",
            "当前分类有未保存的修改，是否保存？",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if reply == QMessageBox.Cancel:
            return False
        if reply == QMessageBox.Save:
            return self._save_current()
        if self._current_key in self.categories:
            self._select_key(self._current_key)
            self._load_category(self._current_key)
        return True

    def _select_key(self, key: str | None) -> None:
        if key is None:
            return
        self._changing_selection = True
        try:
            for row in range(self.cat_list.count()):
                if self.cat_list.item(row).data(Qt.UserRole) == key:
                    self.cat_list.setCurrentRow(row)
                    return
        finally:
            self._changing_selection = False

    def _load_category(self, key: str) -> None:
        cat = self.categories[key]
        proc_list = cat.get("match", {}).get("process_names", [])
        kw_list = cat.get("match", {}).get("title_keywords", [])

        self._loading_editor = True
        try:
            self.edit_name.setText(cat.get("display_name", ""))
            self.edit_processes.setPlainText("\n".join(proc_list))
            self.edit_keywords.setPlainText("\n".join(kw_list))

            rule = cat.get("active_rule", "interactive_required")
            self.edit_rule.setCurrentIndex(_RULE_INDEX.get(rule, 0))
        finally:
            self._loading_editor = False
        self._current_key = key
        self._update_category_meta(key, cat, proc_list, kw_list)
        self._update_match_summary(proc_list, kw_list)
        self._set_dirty(False)

    def _mark_dirty(self, *_args) -> None:
        if not self._loading_editor:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        self._dirty = dirty
        self.btn_save.setEnabled(dirty)

    def _update_category_meta(self, key: str, cat: dict, proc_list: list[str], kw_list: list[str]):
        is_factory = key in self._factory_keys
        self.category_chip.setText("系统保留分类" if is_factory else "自定义分类")
        self.cat_meta.setText(
            f"{cat.get('display_name', key)} · {len(proc_list)} 个进程 · {len(kw_list)} 个关键词"
        )

    def _update_match_summary(self, proc_list: list[str], kw_list: list[str]):
        self.match_hint.setText(
            f"当前配置：{len(proc_list)} 个进程规则，{len(kw_list)} 个标题关键词。"
        )

    def _save_current(self):
        key = self._current_key
        if key is None or key not in self.categories:
            return False
        display_name = self.edit_name.text().strip()
        if not display_name:
            QMessageBox.warning(self, "无法保存", "分类名称不能为空。")
            return False

        candidate = copy.deepcopy(self.categories)
        cat = candidate[key]
        cat["display_name"] = display_name
        cat.setdefault("match", {})
        cat["match"]["process_names"] = list(dict.fromkeys([
            item.strip() for item in self.edit_processes.toPlainText().split("\n") if item.strip()
        ]))
        cat["match"]["title_keywords"] = list(dict.fromkeys([
            item.strip() for item in self.edit_keywords.toPlainText().split("\n") if item.strip()
        ]))
        cat["active_rule"] = _RULE_OPTIONS[self.edit_rule.currentIndex()]["key"]

        if not self._save_to_db(candidate):
            return False
        self.categories = candidate
        self._populate_list()
        self._select_key(key)
        self._load_category(key)
        if self.worker:
            self.worker.reload_classifier()

        QMessageBox.information(self, "保存成功", f"分类“{cat['display_name']}”已更新。")
        return True

    def _rescan_apps(self):
        if not self._resolve_dirty_edits():
            return
        try:
            apps = scan_installed_apps()
            classified = classify_scanned_apps(apps)
            candidate = copy.deepcopy(self.categories)
            added = 0
            for category_key, process_names in classified.items():
                if category_key not in candidate:
                    candidate[category_key] = {
                        "display_name": category_key,
                        "active_rule": "interactive_required",
                        "match": {"process_names": [], "title_keywords": []},
                    }
                match = candidate[category_key].setdefault("match", {})
                existing = list(match.get("process_names", []))
                merged = list(existing)
                seen = {item.casefold() for item in existing}
                for process_name in sorted(process_names, key=str.casefold):
                    if process_name.casefold() in seen:
                        continue
                    merged.append(process_name)
                    seen.add(process_name.casefold())
                added += max(0, len(merged) - len(existing))
                match["process_names"] = merged
            if not self._save_to_db(candidate):
                return
            selected_key = self._current_key
            self.categories = candidate
            self._populate_list()
            self._select_key(selected_key)
            if selected_key:
                self._load_category(selected_key)
            if self.worker:
                self.worker.reload_classifier()
            QMessageBox.information(self, "扫描完成", f"发现 {len(apps)} 个应用，新增 {added} 条分类规则。")
        except Exception as exc:
            QMessageBox.warning(self, "扫描失败", str(exc))

    def _debug_classification(self):
        process, ok = QInputDialog.getText(self, "测试分类", "进程名：")
        if not ok or not process.strip():
            return
        title, ok = QInputDialog.getText(self, "测试分类", "窗口标题：")
        if not ok:
            return
        try:
            result = Classifier(self.config_path, self.db_path).classify(process.strip(), title.strip())
            QMessageBox.information(
                self, "分类结果",
                f"分类：{result.get('category_name', result.get('category_key', '未知'))}\n"
                f"规则：{result.get('category_key', 'unknown')}\n"
                f"策略：{result.get('active_rule', 'unknown')}",
            )
        except Exception as exc:
            QMessageBox.warning(self, "测试失败", str(exc))

    def _add_category(self):
        if not self._resolve_dirty_edits():
            return
        new_key = f"custom_{len(self.categories)}"
        while new_key in self.categories:
            new_key = f"custom_{len(self.categories) + 1}"

        candidate = copy.deepcopy(self.categories)
        candidate[new_key] = {
            "display_name": "新分类",
            "active_rule": "interactive_required",
            "match": {"process_names": [], "title_keywords": []},
        }
        if not self._save_to_db(candidate):
            return
        self.categories = candidate
        self._populate_list()
        if self.worker:
            self.worker.reload_classifier()
        self._select_key(new_key)
        self._load_category(new_key)

    def _delete_current(self):
        row = self.cat_list.currentRow()
        if row < 0:
            return

        key = self.cat_list.item(row).data(Qt.UserRole)
        if key in self._factory_keys:
            QMessageBox.warning(self, "不可删除", "系统保留分类不可删除。")
            return
        if not self._resolve_dirty_edits():
            return

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定删除分类“{self.categories[key]['display_name']}”吗？",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            candidate = copy.deepcopy(self.categories)
            del candidate[key]
            if not self._save_to_db(candidate):
                return
            self.categories = candidate
            if self.worker:
                self.worker.reload_classifier()
            self._populate_list()
            if self.cat_list.count() > 0:
                first_key = self.cat_list.item(0).data(Qt.UserRole)
                self._select_key(first_key)
                self._load_category(first_key)
