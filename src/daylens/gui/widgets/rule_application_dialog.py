"""Application selection; window titles are optional for local tests only."""
from pathlib import Path
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFileDialog,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout)
from .. import style


class RuleApplicationDialog(QDialog):
    def __init__(self, processes, parent=None, *, testing=False, current=''):
        super().__init__(parent)
        self.setWindowTitle('测试本地分类' if testing else '添加应用')
        self.setMinimumWidth(390)
        self.setStyleSheet(style.get_global_style()+style.get_input_style())
        root = QVBoxLayout(self)
        root.setSpacing(10)
        hint = QLabel('选择已有应用，也可输入进程名或浏览可执行文件。')
        hint.setWordWrap(True)
        root.addWidget(hint)
        row = QHBoxLayout()
        self.application = QComboBox()
        self.application.setEditable(True)
        self.application.setInsertPolicy(QComboBox.NoInsert)
        unique = {str(p).strip().casefold():str(p).strip() for p in processes if str(p).strip()}
        self.application.addItems(sorted(unique.values(), key=str.casefold))
        if current:
            self.application.setCurrentText(current)
        row.addWidget(self.application, 1)
        browse = QPushButton('浏览…')
        browse.clicked.connect(self._browse)
        row.addWidget(browse)
        root.addLayout(row)
        self.title_label = QLabel('窗口标题（可选，仅测试网页内容时填写）')
        self.title = QLineEdit()
        self.title.setPlaceholderText('留空即可按应用测试')
        self.title_label.setVisible(testing)
        self.title.setVisible(testing)
        root.addWidget(self.title_label)
        root.addWidget(self.title)
        self.notice = QLabel('仅测试当前本地草稿，不包含人工纠错或AI，不会保存规则。' if testing else '只添加到当前草稿，保存后才生效。')
        self.notice.setWordWrap(True)
        root.addWidget(self.notice)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText('测试' if testing else '添加')
        buttons.button(QDialogButtonBox.Cancel).setText('取消')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def selected_process(self):
        return self.application.currentText().strip().replace('\\','/').rsplit('/',1)[-1]

    def selected_title(self):
        return self.title.text().strip()

    def accept(self):
        if not self.selected_process():
            self.notice.setText('请先选择应用或填写进程名。')
            return
        super().accept()

    def _browse(self):
        selected, _filter = QFileDialog.getOpenFileName(self, '选择应用', '', '应用程序 (*.exe);;所有文件 (*)')
        if selected:
            self.application.setCurrentText(Path(selected).name)
