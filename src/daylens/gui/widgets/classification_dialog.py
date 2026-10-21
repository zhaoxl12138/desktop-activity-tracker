"""Theme-aware, explicit classification correction dialogs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout
from .. import style

from ...category_registry import category_choices
CATEGORY_CHOICES = category_choices()


class ChoiceDialog(QDialog):
    """Select an item using stable item data rather than display text."""
    def __init__(self, parent=None, *, heading, description, choices):
        super().__init__(parent)
        self.setWindowTitle(heading)
        self.setMinimumWidth(460)
        c = style.COLORS
        self.setStyleSheet(style.get_input_style() + f'''
            QDialog {{ background: {c['panel_bg']}; color: {c['text']}; }}
            QLabel {{ color: {c['text']}; font-size: 14px; }}
            QComboBox QAbstractItemView {{ background: {c['panel_bg_alt']};
                color: {c['text']}; selection-background-color: {c['primary']};
                selection-color: white; padding: 6px; }}
            QPushButton {{ background: {c['panel_bg_alt']}; color: {c['text']};
                border: 1px solid {c['border']}; padding: 8px 18px; border-radius: 6px; }}
            QPushButton:default {{ background: {c['primary']}; color: white; }}
        ''')
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(22, 20, 22, 20)
        self.root.setSpacing(14)
        self.title_label = self.add_label(description)
        self.category_combo = QComboBox()
        self.category_combo.setMinimumHeight(40)
        for name, value in choices:
            self.category_combo.addItem(name, value)
        self.root.addWidget(self.category_combo)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('保存分类')
        self.buttons.button(QDialogButtonBox.Cancel).setText('取消')
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.root.addWidget(self.buttons)

    def add_label(self, text):
        label = QLabel(str(text))
        label.setTextFormat(Qt.PlainText)
        label.setWordWrap(True)
        self.root.addWidget(label)
        return label

    def selected_category(self):
        return self.category_combo.currentData()


class ClassificationDialog(ChoiceDialog):
    def __init__(self, *, app_name, title, current_category, parent=None, categories=None):
        super().__init__(parent, heading='纠正分类', description=title, choices=category_choices(categories))
        self.app_label = self.add_label(f'应用：{app_name}')
        self.root.insertWidget(0, self.app_label)
        index = self.category_combo.findData(current_category)
        self.category_combo.setCurrentIndex(max(0, index))
        self.add_label('作用范围')
        self.scope_combo = QComboBox()
        self.scope_combo.addItem('当前标题及同应用的相似标题', 'similar')
        self.scope_combo.addItem('仅当前完整标题', 'exact')
        self.root.addWidget(self.scope_combo)
        self.add_label('原分类：' + dict((key,name) for name,key in category_choices(categories)).get(current_category, current_category))
        self.add_label('保存后对后续记录生效')
        self.media_hint = self.add_label('影音分类可能影响后续被动播放计时')
        self.category_combo.currentIndexChanged.connect(self._refresh_hint)
        self._refresh_hint()
        self.root.removeWidget(self.buttons)
        self.root.addWidget(self.buttons)

    def _refresh_hint(self):
        self.media_hint.setVisible(self.selected_category() == 'video')

    def selected_scope(self):
        return self.scope_combo.currentData()
