"""Manual, budgeted review generation with a plain-text evidence viewer."""

import queue
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QComboBox, QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ...services.intelligence_report_service import generate_budget_review, render_review
from .. import style as ui_style


class IntelligenceReviewBar(QWidget):
    def __init__(self, db_path, parent=None):
        super().__init__(parent)
        self.db_path = db_path
        self.results = queue.Queue()
        self._stale_kind = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.period = QComboBox()
        self.period.addItem('今日主题与复盘', 'daily')
        self.period.addItem('本周复盘（使用日报摘要）', 'weekly')
        self.period.addItem('本月复盘（使用周报摘要）', 'monthly')
        layout.addWidget(self.period)
        self.button = QPushButton('生成 / 查看智能复盘')
        self.button.setStyleSheet(ui_style.get_button_secondary_style())
        self.period.setStyleSheet(ui_style.get_input_style())
        self.period.currentIndexChanged.connect(self._sync_button)
        self.button.clicked.connect(self._generate)
        layout.addWidget(self.button)
        self.status = QLabel('每周期最多生成一次，使用统一月预算')
        self.status.setWordWrap(True)
        layout.addWidget(self.status, 1)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self._poll)

    def _sync_button(self, *_args):
        stale = self._stale_kind == self.period.currentData()
        self.button.setText('重新分析旧数据' if stale else '生成 / 查看智能复盘')

    def _generate(self):
        kind, db_path, results = self.period.currentData(), self.db_path, self.results
        regenerate = self._stale_kind == kind
        if regenerate and QMessageBox.question(
            self,
            '重新分析旧数据',
            '历史分类或记录已经变化。重新分析会产生一次新的 API 请求，是否继续？',
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        ) != QMessageBox.Yes:
            return
        self.button.setEnabled(False)
        self.status.setText('正在整理并生成…')
        def run():
            try:
                results.put((True, generate_budget_review(
                    db_path, kind, regenerate_stale=regenerate
                )))
            except Exception as exc:
                results.put((False, str(exc)))
        threading.Thread(target=run, name='DayLens-AI-review', daemon=True).start()
        self.timer.start()

    def _poll(self):
        try:
            success, result = self.results.get_nowait()
        except queue.Empty:
            return
        self.timer.stop()
        self.button.setEnabled(True)
        if not success:
            self.status.setText(result)
            return
        if result.get('evidence_status') == 'stale':
            self._stale_kind = self.period.currentData()
            self.button.setText('重新分析旧数据')
            self.status.setText('当前汇总基于旧数据；查看不扣费，重新分析会产生新请求')
        else:
            self._stale_kind = None
            self.button.setText('生成 / 查看智能复盘')
            self.status.setText('已保存，可重复查看；原生报告保持独立')
        dialog = QDialog(self)
        dialog.setWindowTitle('智能复盘与依据')
        dialog.resize(700, 500)
        layout = QVBoxLayout(dialog)
        text = QPlainTextEdit()
        text.setReadOnly(True)
        text.setPlainText(render_review(result))
        layout.addWidget(text)
        dialog.exec()
