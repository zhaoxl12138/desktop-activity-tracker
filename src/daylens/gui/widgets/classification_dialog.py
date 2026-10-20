"""Theme-aware, explicit classification correction dialogs."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout
from .. import style

CATEGORY_CHOICES = (
    ('技术学习 / 开发', 'coding'), ('阅读学习', 'reading'),
    ('办公 / 求职', 'office'), ('AI工具', 'ai_tools'),
    ('设计创作', 'creative'), ('社交通讯', 'social'),
    ('系统工具', 'tools'), ('游戏娱乐', 'gaming'),
    ('投资理财', 'finance'),
    ('影音娱乐', 'video'), ('浏览器', 'browser_general'), ('其他', 'other'),
)


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
    def __init__(self, *, app_name, title, current_category, parent=None):
        super().__init__(parent, heading='纠正分类', description=title, choices=CATEGORY_CHOICES)
        self.app_label = self.add_label(f'应用：{app_name}')
        self.root.insertWidget(0, self.app_label)
        index = self.category_combo.findData(current_category)
        self.category_combo.setCurrentIndex(max(0, index))
        self.add_label('保存后对后续记录生效')
        self.media_hint = self.add_label('影音分类可能影响后续被动播放计时')
        self.category_combo.currentIndexChanged.connect(self._refresh_hint)
        self._refresh_hint()
        self.root.removeWidget(self.buttons)
        self.root.addWidget(self.buttons)

    def _refresh_hint(self):
        self.media_hint.setVisible(self.selected_category() == 'video')
