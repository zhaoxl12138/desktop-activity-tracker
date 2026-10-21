"""One workspace for pending suggestions, manual decisions and local rules."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QPushButton, QMessageBox, QDialog, QScrollArea)
from ...category_registry import category_choices
from ...services.classification_decisions import (decision_command, undo_last,
    set_decision_enabled, update_decision_category, delete_decision)
from ...services.intelligence_state import load_overrides
from ...services.intelligence_evidence import (load_patterns, set_pattern_enabled,
    update_pattern_category, delete_pattern)
from ..widgets.classification_dialog import ClassificationDialog
from .. import style


class ClassificationManagementPage(QWidget):
    @property
    def worker(self):
        return self.rules_editor.worker

    @worker.setter
    def worker(self, value):
        self.rules_editor.worker = value

    def __getattr__(self, name):
        # Compatibility for integrations that previously addressed the rules page.
        editor = self.__dict__.get('rules_editor')
        if editor is not None and hasattr(editor, name):
            return getattr(editor, name)
        raise AttributeError(name)

    def __init__(self, live, rules):
        super().__init__()
        self.live = live
        self.rules_editor = rules
        self._rows = []
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        heading = QLabel('分类管理')
        heading.setStyleSheet(f"font-size:22px;font-weight:700;color:{style.COLORS['text']}")
        root.addWidget(heading)
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(style.get_input_style() + f'''
            QTabWidget::pane {{ border:1px solid {style.COLORS['border']}; }}
            QTabBar::tab {{ padding:8px 14px; color:{style.COLORS['text']};
                background:{style.COLORS['panel_bg']}; }}
            QTabBar::tab:selected {{ background:{style.COLORS['primary']}; color:white; }}
        ''')
        root.addWidget(self.tabs, 1)
        pending = QWidget()
        pending_layout = QVBoxLayout(pending)
        self.empty_pending = QLabel('暂无待确认分类')
        pending_layout.addWidget(self.empty_pending)
        pending_layout.addWidget(live.review_card)
        pending_layout.addStretch(1)
        self.tabs.addTab(pending, '待确认')
        manual = QWidget()
        layout = QVBoxLayout(manual)
        hint = QLabel('启停默认影响此次决定的精确标题与关联模式；旧版未关联决定保持独立。仅对后续记录生效。')
        hint.setWordWrap(True)
        hint.setTextFormat(Qt.PlainText)
        layout.addWidget(hint)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['应用','标题 / 示例','分类','范围 / 关联','状态','命中','最近命中'])
        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.SingleSelection)
        self.table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.table.verticalHeader().hide()
        self.table.setStyleSheet(style.get_table_style())
        self.table.setMaximumHeight(230)
        layout.addWidget(self.table, 1)
        actions = QHBoxLayout()
        for text, method in [('修改分类',self._edit), ('启用 / 停用',self._toggle),
                             ('仅停用相似扩展',self._disable_expansion), ('删除决定',self._delete),
                             ('撤销最近操作',self._undo), ('刷新',self.refresh)]:
            button = QPushButton(text)
            button.setMinimumHeight(32)
            button.setStyleSheet(style.get_button_secondary_style())
            button.clicked.connect(method)
            actions.addWidget(button)
        layout.addLayout(actions)
        layout.addStretch(1)
        self.status = QLabel('等待操作')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.tabs.addTab(manual, '人工纠错')
        rules_scroll = QScrollArea()
        rules_scroll.setWidgetResizable(True)
        rules_scroll.setWidget(rules)
        rules_scroll.setFrameShape(QScrollArea.NoFrame)
        self.tabs.addTab(rules_scroll, '本地规则')
        footer = QHBoxLayout()
        footer.addWidget(self.status,1)
        self.retry = QPushButton('重试应用')
        self.retry.clicked.connect(live.classification_corrected.emit)
        self.retry.hide()
        footer.addWidget(self.retry)
        root.addLayout(footer)
        root.removeItem(footer)
        root.insertLayout(1,footer)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self._refresh_safely)
        live.classification_corrected.connect(self._saved_status)
        self.refresh()

    def _saved_status(self):
        self.status.setText(self.live.correction_status.text())
        self.retry.show()
        self.refresh()

    def on_classification_applied(self, revision):
        self.status.setText(self.live.correction_status.text())
        self.retry.setVisible(not self.live.apply_retry_button.isHidden())

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_safely()
        self.timer.start()

    def hideEvent(self, event):
        self.timer.stop()
        super().hideEvent(event)

    def _refresh_safely(self):
        try:
            self.refresh()
        except Exception as exc:
            self.status.setText('读取分类状态失败：'+str(exc))

    def refresh(self):
        if hasattr(self.rules_editor,'categories'):
            self.live.categories = self.rules_editor.categories
        self.live.refresh_reviews(force=True)
        self.empty_pending.setVisible(not bool(getattr(self.live,'_review_rows',[])))
        selected = self._selected()
        selected_id = selected.get('id') if selected else None
        directory = self.live._review_directory()
        decisions = load_overrides(directory)
        patterns = {p['id']:p for p in load_patterns(directory)}
        names = dict((key,name) for name,key in category_choices(self.live.categories))
        self._rows = []
        linked = set()
        for identity, value in decisions.items():
            pattern = patterns.get(value.get('pattern_id'), {})
            linked.add(value.get('pattern_id'))
            self._rows.append(dict(value, id=identity, kind='exact',
                display_app=value.get('app', '旧版未保存'), display_title=value.get('title', '旧版精确决定 · '+identity[:8]),
                relation='精确 + 关联相似' if pattern else '仅精确（独立）',
                hit_count=int(value.get('hit_count',0))+int(pattern.get('hit_count',0)),
                last_used_at=max(value.get('last_used_at',''),pattern.get('last_used_at','')) or '--'))
        for identity, value in patterns.items():
            if identity not in linked:
                self._rows.append(dict(value, kind='pattern', display_app=value.get('app',''),
                    display_title=value.get('example',''), relation='相似（独立）'))
        self.table.setRowCount(len(self._rows))
        self.table.clearSelection()
        self.table.setCurrentCell(-1,-1)
        for index, row in enumerate(self._rows):
            values = [row['display_app'],row['display_title'],names.get(row['category'],row['category']),
                row['relation'],'启用' if row.get('enabled',True) else '停用',str(row.get('hit_count',0)),
                row.get('last_used_at','--')]
            for column, value in enumerate(values):
                item = QTableWidgetItem(str(value))
                item.setToolTip(str(value).replace('<','&lt;'))
                self.table.setItem(index,column,item)
            if row['id'] == selected_id:
                self.table.selectRow(index)

    def _selected(self):
        row = self.table.currentRow() if hasattr(self,'table') else -1
        return self._rows[row] if 0 <= row < len(self._rows) else None

    def _execute(self, command, *args):
        try:
            result = command(self.live._review_directory(), *args)
            if result is False:
                self.status.setText('没有可更新的决定或可撤销的操作')
                return
            self.live._decision_saved('分类决定已更新')
            self.refresh()
        except Exception as exc:
            QMessageBox.warning(self,'未能更新',str(exc))

    def _edit(self):
        row = self._selected()
        if row is None:
            return
        dialog = ClassificationDialog(app_name=row['display_app'], title=row['display_title'],
            current_category=row['category'], categories=self.live.categories, parent=self)
        dialog.scope_combo.hide()
        if dialog.exec() == QDialog.Accepted:
            method = update_decision_category if row['kind']=='exact' else decision_command(update_pattern_category)
            if row['kind']=='exact':
                self._execute(lambda directory,identity,category: method(directory,identity,category,
                    categories=self.live.categories),row['id'],dialog.selected_category())
            else:
                self._execute(lambda directory,identity,category: method(directory,identity,category,
                    categories=self.live.categories),row['id'],dialog.selected_category())

    def _toggle(self):
        row = self._selected()
        if row:
            method = set_decision_enabled if row['kind']=='exact' else decision_command(set_pattern_enabled)
            self._execute(method,row['id'],not row.get('enabled',True))

    def _disable_expansion(self):
        row = self._selected()
        identity = (row.get('pattern_id') if row['kind']=='exact' else row['id']) if row else None
        if identity:
            self._execute(decision_command(lambda directory, key: set_pattern_enabled(
                directory,key,False,include_exact=False)),identity)

    def _delete(self):
        row = self._selected()
        if row and QMessageBox.question(self,'删除决定','删除此决定及其独占关联模式？不会修改历史记录。',
                QMessageBox.Yes|QMessageBox.No) == QMessageBox.Yes:
            method = delete_decision if row['kind']=='exact' else decision_command(delete_pattern)
            self._execute(method,row['id'])

    def _undo(self):
        self._execute(undo_last)

    def has_unsaved_changes(self):
        method = getattr(self.rules_editor,'has_unsaved_changes',None)
        return bool(method and method())
