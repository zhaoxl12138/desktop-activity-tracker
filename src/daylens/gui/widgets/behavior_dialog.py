"""Report-center local evidence viewer. Background reads do not block Qt."""
import queue
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QPushButton, QTextBrowser, QVBoxLayout

from ...services.behavior_profile_service import load_profiles, profile_lines
from .. import style


class BehaviorDialog(QDialog):
    def __init__(self, db_path, directory, parent=None):
        super().__init__(parent)
        self.db_path, self.directory = db_path, directory
        self.model = None
        self.results = queue.Queue()
        self.setWindowTitle("本地行为画像")
        self.resize(780, 540)
        layout = QVBoxLayout(self)
        self.text = QTextBrowser()
        layout.addWidget(self.text, 1)
        row = QHBoxLayout()
        row.addStretch()
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.setStyleSheet(style.get_button_secondary_style())
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        self.refresh_button.clicked.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.refresh()

    def refresh(self):
        self.refresh_button.setEnabled(False)
        self.text.setPlainText("正在读取本地可信记录…")
        db, directory, results = self.db_path, self.directory, self.results
        def read():
            try:
                model = load_profiles(db, directory)
                results.put(model)
            except Exception:
                results.put({"status": "unavailable", "profiles": {}})
        threading.Thread(target=read, daemon=True).start()

    def poll(self):
        try:
            self.model = self.results.get_nowait()
        except queue.Empty:
            return
        if self.model["status"] == "disabled":
            self.text.setPlainText("请在设置中心开启“本地行为画像”。无需API密钥。")
        else:
            self.text.setPlainText("\n".join(profile_lines(self.model)))
        self.refresh_button.setEnabled(True)
