"""Compact opt-in AI settings. Network work never executes on the GUI thread."""

from __future__ import annotations

import queue
import threading
from pathlib import Path

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QCheckBox, QDoubleSpinBox, QGroupBox, QHBoxLayout,
                               QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ... import get_data_dir
from ...services import intelligence_credentials as credentials
from ...services.intelligence_budget import IntelligenceBudget
from ...services.intelligence_client import DeepSeekProvider
from ...services.intelligence_state import load_settings, save_settings
from .. import style as ui_style


class IntelligenceSettings(QGroupBox):
    def __init__(self, worker=None, parent=None, *, directory=None):
        super().__init__('DeepSeek · 省钱模式', parent)
        self.worker = worker
        self.directory = Path(directory or Path(get_data_dir()) / 'intelligence')
        self.results = queue.Queue()
        settings = load_settings(self.directory)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 20, 16, 16)
        root.setSpacing(10)
        self.enabled = QCheckBox('启用智能增强（发送脱敏标题、应用名称及汇总事实）')
        self.enabled.setChecked(settings['enabled'])
        root.addWidget(self.enabled)
        self.classification = QCheckBox('智能分类：主动使用30秒后判断，每天最多30个新标题')
        self.classification.setChecked(settings['classification_enabled'])
        root.addWidget(self.classification)
        self.reports = QCheckBox('自动汇总：每天23:00日报 · 周日周报 · 月末月报')
        self.reports.setChecked(settings['reports_enabled'])
        root.addWidget(self.reports)
        hint = QLabel('Flash非思考模式 · 最多5个标题一批 · 本地缓存复用 · 月预算内停止新请求')
        hint.setWordWrap(True)
        root.addWidget(hint)
        row = QHBoxLayout()
        row.addWidget(QLabel('每月预算（元）'))
        self.budget = QDoubleSpinBox()
        self.budget.setRange(0, 5)
        self.budget.setDecimals(2)
        self.budget.setMinimumWidth(110)
        self.budget.setMinimumHeight(36)
        self.budget.setValue(settings['monthly_budget_micros'] / 1_000_000)
        row.addWidget(self.budget)
        row.addStretch()
        root.addLayout(row)
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText('输入API密钥，仅存Windows凭据管理器')
        self.key.setMaxLength(512)
        root.addWidget(self.key)
        self.key_state = QLabel('已保存密钥' if credentials.read_key() else '尚未配置密钥')
        root.addWidget(self.key_state)
        row = QHBoxLayout()
        self.save_key_button = QPushButton('保存密钥')
        self.delete_key_button = QPushButton('删除密钥')
        self.test_button = QPushButton('测试连接')
        for button in (self.save_key_button, self.delete_key_button, self.test_button):
            row.addWidget(button)
        root.addLayout(row)
        self.apps = QLineEdit(', '.join(settings['excluded_apps']))
        self.apps.setPlaceholderText('排除应用：用逗号分隔进程名，例如 secret.exe')
        root.addWidget(self.apps)
        self.words = QLineEdit(', '.join(settings['excluded_words']))
        self.words.setPlaceholderText('排除标题关键词：用逗号分隔，例如 客户名称, 私人')
        root.addWidget(self.words)
        self.save_button = QPushButton('保存智能设置')
        root.addWidget(self.save_button)
        self.usage = QLabel('')
        self.usage.setTextFormat(Qt.PlainText)
        self.usage.setWordWrap(True)
        root.addWidget(self.usage)
        self.status = QLabel('')
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        for button in (self.save_key_button, self.delete_key_button, self.test_button):
            button.setStyleSheet(ui_style.get_button_secondary_style())
        self.save_button.setStyleSheet(ui_style.get_button_primary_style())
        for edit in (self.key, self.apps, self.words, self.budget):
            edit.setStyleSheet(ui_style.get_input_style())
        for label in (self.key_state, self.usage, self.status, hint):
            label.setStyleSheet(f"color: {ui_style.COLORS['text_secondary']}; font-size: 12px;")
        self.save_key_button.clicked.connect(self._save_key)
        self.delete_key_button.clicked.connect(self._delete_key)
        self.save_button.clicked.connect(self._save)
        self.test_button.clicked.connect(self._test)
        self.timer = QTimer(self)
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self._poll)
        self.timer.start()
        self._usage_ticks = 0
        self._refresh_usage()

    def _reload_worker(self):
        reload = getattr(self.worker, 'reload_intelligence', None)
        if callable(reload):
            reload()

    def _save_key(self):
        try:
            credentials.save_key(self.key.text())
            self.key.clear()
            self.key_state.setText('已保存密钥')
            self._reload_worker()
        except Exception as exc:
            QMessageBox.warning(self, '密钥保存失败', str(exc))

    def _delete_key(self):
        try:
            credentials.delete_key()
            self.key.clear()
            self.key_state.setText('尚未配置密钥')
            self.enabled.setChecked(False)
            self._save()
        except Exception as exc:
            QMessageBox.warning(self, '删除失败', str(exc))

    def _save(self):
        try:
            save_settings(self.directory, {
                'enabled': self.enabled.isChecked(),
                'classification_enabled': self.classification.isChecked(),
                'reports_enabled': self.reports.isChecked(),
                'monthly_budget_micros': round(self.budget.value() * 1_000_000),
                'excluded_apps': [x.strip() for x in self.apps.text().replace('，', ',').split(',') if x.strip()],
                'excluded_words': [x.strip() for x in self.words.text().replace('，', ',').split(',') if x.strip()],
            })
            self._reload_worker()
            self.status.setText('智能设置已保存；只影响后续记录')
            self._refresh_usage()
        except Exception as exc:
            QMessageBox.warning(self, '保存失败', str(exc))

    def _refresh_usage(self):
        try:
            settings = load_settings(self.directory)
            snapshot = IntelligenceBudget(self.directory / 'budget.json', settings['monthly_budget_micros']).snapshot()
            self.usage.setText(
                f"本月保守估算 ¥{snapshot['cost_micros']/1_000_000:.3f} / ¥{snapshot['budget_micros']/1_000_000:.2f}"
                f"　今日 {snapshot['today_titles']}/30 个标题 · {snapshot['today_requests']} 次请求"
                f"\n按高峰未缓存价格估算；未确认请求保留预算，以服务商账单为准")
        except Exception:
            self.usage.setText('AI用量暂不可读，自动请求将保守暂停')

    def _test(self):
        if not credentials.read_key():
            self.status.setText('请先保存API密钥')
            return
        self.test_button.setEnabled(False)
        self.status.setText('正在发送固定测试文本，不发送浏览记录…')
        directory, results = self.directory, self.results
        def run():
            try:
                settings = load_settings(directory)
                provider = DeepSeekProvider(IntelligenceBudget(directory / 'budget.json', settings['monthly_budget_micros']), credentials.read_key)
                result = provider.request_json('Return JSON {"ok":true}.', {}, kind='connection_test',
                                               daily_limit=3, output_limit=32)
                results.put('连接成功' if result.get('ok') is True else '服务可达，但测试格式不匹配')
            except Exception:
                results.put('连接未成功，请检查密钥、网络或月预算')
        threading.Thread(target=run, name='DayLens-AI-test', daemon=True).start()

    def _poll(self):
        self._usage_ticks += 1
        if self._usage_ticks % 10 == 0 and self.isVisible():
            self._refresh_usage()
        try:
            message = self.results.get_nowait()
        except queue.Empty:
            return
        self.test_button.setEnabled(True)
        self.status.setText(message)
        self._refresh_usage()
