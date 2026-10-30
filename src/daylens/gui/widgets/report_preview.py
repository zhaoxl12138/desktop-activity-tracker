"""Safe Qt Markdown reader with independent single-flight local file loading."""

from __future__ import annotations

import queue
import threading
import re

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import (
    QDesktopServices,
    QKeySequence,
    QShortcut,
    QTextCursor,
    QTextDocument,
)
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...services.report_preview_service import (
    PreviewCache,
    summary_status,
    native_status,
)
from .. import style


class SafeReportBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setOpenLinks(False)
        self.setOpenExternalLinks(False)
        self.anchorClicked.connect(self._open_link)

    def loadResource(self, resource_type, name):  # noqa: N802
        return QByteArray()  # Never delegate to Qt's local/network loaders.

    def _open_link(self, url):
        if url.toString().startswith("#"):
            self.scrollToAnchor(url.fragment())
        elif url.scheme() in {"https", "http"} and not url.userInfo():
            if (
                QMessageBox.question(
                    self,
                    "打开外部链接",
                    "是否在浏览器中打开？\n" + url.toDisplayString(),
                )
                == QMessageBox.Yes
            ):
                QDesktopServices.openUrl(url)


class ReportPreview(QWidget):
    def __init__(self, reports_dir, db_path="", parent=None):
        super().__init__(parent)
        self.cache = PreviewCache(reports_dir)
        self.db_path = db_path
        self._generation = 0
        self._worker_active = False
        self._status_active = False
        self._status_pending = None
        self._pending = None
        self._closed = False
        self._results = queue.Queue()
        self._last_path = None
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(6)
        toolbar = QHBoxLayout()
        self.toc = QComboBox()
        self.toc.setMinimumContentsLength(6)
        self.toc.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.toc.setToolTip("小节目录")
        self.toc.setMinimumWidth(0)
        toolbar.addWidget(self.toc, 1)
        self.retry = QPushButton("刷新")
        self.retry.clicked.connect(self.reload)
        self.find_button = QPushButton("查找")
        self.find_button.clicked.connect(self.show_search)
        toolbar.addWidget(self.find_button)
        toolbar.addWidget(self.retry)
        root.addLayout(toolbar)
        self.search_panel = QWidget()
        search_row = QHBoxLayout(self.search_panel)
        search_row.setContentsMargins(0, 0, 0, 0)
        self.search = QLineEdit()
        self.search.setPlaceholderText("查找正文 · Ctrl+F")
        self.search.returnPressed.connect(self.find_next)
        search_row.addWidget(self.search, 1)
        self.previous = QPushButton("↑")
        self.next = QPushButton("↓")
        self.previous.setToolTip("上一个匹配")
        self.next.setToolTip("下一个匹配")
        self.previous.clicked.connect(lambda: self.find_next(backward=True))
        self.next.clicked.connect(self.find_next)
        search_row.addWidget(self.previous)
        search_row.addWidget(self.next)
        root.addWidget(self.search_panel)
        self.search_panel.hide()
        self.status = QLabel("选择报告后在此预览")
        self.status.setWordWrap(True)
        root.addWidget(self.status)
        self.browser = SafeReportBrowser()
        self.browser.setMinimumHeight(40)
        self.browser.setMinimumWidth(0)
        self.browser.setStyleSheet(
            f"QTextBrowser {{ background:{style.COLORS['panel_bg']}; color:{style.COLORS['text']}; border:0; padding:12px; }}"
        )
        self.browser.document().setDefaultStyleSheet(
            "table {border-collapse:collapse;} td,th {padding:6px; border:1px solid #52708e;} pre {white-space:pre-wrap;}"
        )
        root.addWidget(self.browser, 1)
        self.toc.activated.connect(self._jump)
        shortcut = QShortcut(QKeySequence.Find, self)
        shortcut.setContext(Qt.WidgetWithChildrenShortcut)
        shortcut.activated.connect(self.show_search)
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._poll)
        self.timer.start()

    def load_report(self, path):
        if self._closed:
            return
        self._last_path = str(path)
        self._generation += 1
        self._pending = (self._generation, str(path))
        self.status.setText("正在读取本地报告…")
        self._start()

    def reload(self):
        if self._last_path:
            self.load_report(self._last_path)

    def clear(self, message="选择一份报告以预览"):
        self._generation += 1
        self._pending = None
        self._status_pending = None
        self._last_path = None
        self.toc.clear()
        self.browser.setPlainText(message)
        self.status.setText("本地只读预览 · 不产生 API 费用")

    def suspend(self):
        self._generation += 1
        self._pending = None
        self._status_pending = None

    def _start(self):
        if self._worker_active or not self._pending or self._closed:
            return
        generation, path = self._pending
        self._pending = None
        self._worker_active = True
        cache, results, db_path = self.cache, self._results, self.db_path

        def read():
            try:
                payload = cache.load(path)
                payload["summary_status"] = (
                    "文件较大，当前为有限文本预览"
                    if payload["truncated"]
                    else "正文已加载 · 正在核验汇总状态…"
                )
                results.put((generation, "document", payload))
            except Exception as exc:
                results.put((generation, "error", str(exc)))
            finally:
                results.put((generation, "done", None))

        threading.Thread(
            target=read, name="DayLens-report-preview", daemon=True
        ).start()

    def _poll(self):
        try:
            generation, phase, result = self._results.get_nowait()
        except queue.Empty:
            return
        if phase == "done":
            self._worker_active = False
        elif phase == "status_done":
            self._status_active = False
        if not self._closed and generation == self._generation:
            if phase == "document":
                self._display(result)
                if not result["truncated"]:
                    self._status_pending = (generation, result["text"])
            elif phase == "status":
                self.status.setText(str(result))
            elif phase == "error":
                self.status.setText("读取失败，可点击刷新重试：" + result)
        self._start()
        self._start_status()

    def _start_status(self):
        if self._status_active or self._status_pending is None or self._closed:
            return
        generation, content = self._status_pending
        self._status_pending = None
        self._status_active = True
        results, db_path = self._results, self.db_path

        def check():
            try:
                state = " · ".join(
                    part
                    for part in (
                        native_status(db_path, content),
                        summary_status(db_path, content),
                    )
                    if part
                )
                results.put((generation, "status", state))
            except Exception:
                results.put((generation, "status", "当前无法核验，原文仍可查看"))
            finally:
                results.put((generation, "status_done", None))

        threading.Thread(
            target=check, name="DayLens-report-status", daemon=True
        ).start()

    def _display(self, payload):
        self.status.setText(payload["summary_status"])
        if payload["truncated"]:
            self.browser.setPlainText(payload["text"])
        else:
            # Keep machine-only identities out of the reader without enabling
            # raw HTML rendering. Unknown HTML remains literal, never executed.
            visible = re.sub(
                r"<!-- (?:daylens-report:|daylens-ai-evidence:|fact:)[^\n]* -->",
                "",
                payload["text"],
            )
            visible = visible.replace("<!-- daylens-ai-summary:start -->", "").replace(
                "<!-- daylens-ai-summary:end -->", ""
            )
            self.browser.document().setMarkdown(
                visible,
                QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML,
            )
        self.toc.clear()
        block = self.browser.document().begin()
        while block.isValid():
            if block.blockFormat().headingLevel():
                self.toc.addItem(block.text(), block.position())
            block = block.next()

    def _jump(self, index):
        position = self.toc.itemData(index)
        if position is not None:
            cursor = self.browser.textCursor()
            cursor.setPosition(position)
            self.browser.setTextCursor(cursor)
            self.browser.ensureCursorVisible()

    def show_search(self):
        self.search_panel.show()
        self.search.setFocus()

    def find_next(self, *_args, backward=False):
        value = self.search.text()
        if not value:
            return
        flags = QTextDocument.FindBackward if backward else QTextDocument.FindFlags()
        if not self.browser.find(value, flags):
            cursor = self.browser.textCursor()
            cursor.movePosition(QTextCursor.End if backward else QTextCursor.Start)
            self.browser.setTextCursor(cursor)
            if not self.browser.find(value, flags):
                self.status.setText("未找到匹配文本")

    def closeEvent(self, event):  # noqa: N802
        self._closed = True
        self._generation += 1
        self._pending = None
        self.timer.stop()
        super().closeEvent(event)
