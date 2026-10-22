"""Report-center local evidence viewer. Background reads do not block Qt."""
import queue
import threading

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTextBrowser, QVBoxLayout

from ...services.behavior_profile_service import load_profiles, profile_lines
from ...services.behavior_experiment_service import ExperimentStore, SUGGESTION, feedback
from .. import style


class BehaviorDialog(QDialog):
    def __init__(self, db_path, directory, parent=None):
        super().__init__(parent)
        self.db_path, self.directory = db_path, directory
        self.model = None
        self.results = queue.Queue()
        self.setWindowTitle("行为画像与一周实验")
        self.resize(780, 540)
        layout = QVBoxLayout(self)
        self.text = QTextBrowser()
        layout.addWidget(self.text, 1)
        hint = QLabel(SUGGESTION)
        hint.setWordWrap(True)
        layout.addWidget(hint)
        row = QHBoxLayout()
        self.accept_button = QPushButton("接受一周实验")
        self.stop_button = QPushButton("停止实验")
        self.refresh_button = QPushButton("刷新")
        for button in (self.accept_button, self.stop_button, self.refresh_button):
            button.setStyleSheet(style.get_button_secondary_style())
            row.addWidget(button)
        layout.addLayout(row)
        self.accept_button.clicked.connect(self.accept_experiment)
        self.stop_button.clicked.connect(self.stop_experiment)
        self.refresh_button.clicked.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()
        self.refresh()

    def refresh(self):
        for button in (self.accept_button, self.stop_button, self.refresh_button):
            button.setEnabled(False)
        self.text.setPlainText("正在读取本地可信记录…")
        db, directory, results = self.db_path, self.directory, self.results
        def read():
            try:
                model = load_profiles(db, directory)
                experiment = ExperimentStore(directory).load() if model["status"] == "ready" else None
                result = feedback(db, directory) if experiment else "尚未接受实验。"
                results.put((model, experiment, result))
            except Exception:
                results.put(({"status": "unavailable", "profiles": {}}, None, "实验记录暂不可读。"))
        threading.Thread(target=read, daemon=True).start()

    def poll(self):
        try:
            self.model, experiment, result = self.results.get_nowait()
        except queue.Empty:
            return
        if self.model["status"] == "disabled":
            self.text.setPlainText("请在设置中心开启“本地行为画像与一周实验”。无需API密钥。")
        else:
            self.text.setPlainText("\n".join(profile_lines(self.model)) + "\n一周实验\n" + result)
        baseline = self.model["profiles"].get(7, {})
        active = bool(experiment and experiment["status"] == "accepted")
        self.accept_button.setEnabled(bool(baseline.get("ready") and baseline.get("insertion_rate") is not None and not active))
        self.stop_button.setEnabled(active)
        self.refresh_button.setEnabled(True)

    def accept_experiment(self):
        if not self.model or not self.accept_button.isEnabled():
            return
        try:
            ExperimentStore(self.directory).accept(self.model["profiles"][7])
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "实验未开始", str(exc))
        self.refresh()

    def stop_experiment(self):
        try:
            ExperimentStore(self.directory).stop()
        except (ValueError, RuntimeError, OSError) as exc:
            QMessageBox.warning(self, "实验未更新", str(exc))
        self.refresh()
