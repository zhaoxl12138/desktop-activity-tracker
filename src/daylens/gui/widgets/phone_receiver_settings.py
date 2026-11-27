"""Show the iPhone Screen Time source and Windows receiver controls."""

from pathlib import Path
import sys

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout,
)

from ...services.phone_receiver import ReceiverStatus, manage_receiver, pairing_key_path
from ...services.phone_usage import find_phone_archive
from .. import style as ui_style


class PhoneReceiverSettings(QGroupBox):
    _task_key = "settings:phone-receiver"

    def __init__(self, obsidian_path, archive: Path, background_tasks):
        super().__init__("Windows 手机接收端")
        self._obsidian_path = obsidian_path
        self._tasks = background_tasks
        self._busy = False
        self._manager = None
        self._documentation = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 20, 16, 16)
        layout.setSpacing(10)
        source = QLabel(
            "iPhone 快捷指令每天 00:00 发送昨天的 App 使用时长。Windows 接收后写入 Daylog，"
            "DayLens 从 00:05 起复制到本地。"
        )
        source.setWordWrap(True)
        source.setStyleSheet(f"color: {ui_style.COLORS['text_secondary']};")
        layout.addWidget(source)

        form = QFormLayout()
        form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(form)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(Qt.TextSelectableByMouse)
        form.addRow("接收端状态", self.status)
        self.url = self._read_only_field("iPhone 发送地址")
        self.url.setPlaceholderText("刷新状态后查看")
        self.copy_url = self._button("复制地址", self._copy_url)
        url_row = QHBoxLayout()
        url_row.addWidget(self.url, 1)
        url_row.addWidget(self.copy_url)
        form.addRow("iPhone 发送地址", url_row)
        self.source_archive = self._read_only_field("Daylog 原始归档")
        form.addRow("Daylog 原始归档", self.source_archive)
        form.addRow("DayLens 本地副本", self._read_only_field("DayLens 本地副本", str(archive)))
        key = pairing_key_path()
        pairing = self._read_only_field("配对文件", str(key) if key else "")
        pairing.setToolTip("iPhone 请求头使用 X-Screen-Time-Key。已有配对文件会在启动接收端时继续使用。")
        form.addRow("配对文件", pairing)

        actions = QHBoxLayout()
        self.check_status = self._button("刷新状态", self.refresh)
        self.start_receiver = self._button("启动接收端", lambda: self._request("Start"))
        self.open_guide = self._button("打开部署说明", self._open_guide)
        for button in (self.check_status, self.start_receiver, self.open_guide):
            actions.addWidget(button)
        actions.addStretch()
        layout.addLayout(actions)

        for signal_name, handler in (
            ("task_completed", self._on_completed),
            ("task_failed", self._on_failed),
            ("task_cancelled", self._on_cancelled),
        ):
            signal = getattr(self._tasks, signal_name, None)
            if signal is not None:
                signal.connect(handler)
        self._show_config()

    @staticmethod
    def _read_only_field(name: str, value: str = "") -> QLineEdit:
        field = QLineEdit(value)
        field.setAccessibleName(name)
        field.setReadOnly(True)
        return field

    @staticmethod
    def _button(text: str, callback) -> QPushButton:
        button = QPushButton(text)
        button.setStyleSheet(ui_style.get_button_secondary_style())
        button.clicked.connect(callback)
        return button

    def _show_config(self) -> None:
        archive = find_phone_archive(self._obsidian_path())
        if archive:
            archive = archive.absolute()
        vault = archive.parents[1] if archive else None
        self._manager = vault / "scripts" / "manage_iphone_screen_time.ps1" if vault else None
        self._documentation = vault / "docs" / "iphone-screen-time-deployment.md" if vault else None
        self.source_archive.setText(str(archive) if archive else "")
        self.url.clear()
        if sys.platform != "win32":
            message = "接收端管理仅在 Windows 上可用。"
        elif not archive:
            message = "保存指向 Daylog 的 Obsidian 输出路径后即可管理接收端。"
        elif not self._manager.is_file():
            message = "找不到接收端管理脚本，请先同步最新版 Daylog。"
        else:
            message = "等待检查。"
        self.status.setText(message)
        self._update_actions()

    def _update_actions(self, state: str = "") -> None:
        can_run = bool(
            sys.platform == "win32" and self._tasks is not None
            and self._manager and self._manager.is_file() and not self._busy
        )
        self.check_status.setEnabled(can_run)
        self.start_receiver.setEnabled(can_run and state not in {"Running", "PortInUse"})
        self.copy_url.setEnabled(bool(self.url.text()))
        self.open_guide.setEnabled(bool(self._documentation and self._documentation.is_file()))

    def refresh(self) -> None:
        self._request("Status")

    def _request(self, action: str) -> None:
        if self._busy:
            return
        self._show_config()
        if not self.check_status.isEnabled():
            return
        manager = self._manager
        if self._tasks.submit(self._task_key, lambda: manage_receiver(manager, action)):
            self._busy = True
            self.status.setText("正在启动接收端…" if action == "Start" else "正在检查接收端…")
            self._update_actions()

    def _on_completed(self, key: str, result: object) -> None:
        if key != self._task_key or not isinstance(result, ReceiverStatus):
            return
        self._busy = False
        labels = {
            "Running": f"运行中 · {result.interface}",
            "Stopped": "已停止",
            "PortInUse": "端口已占用，请检查是否有旧版接收端在运行。",
        }
        self.status.setText(labels.get(result.state, "状态未知"))
        self.url.setText(result.url)
        self._update_actions(result.state)

    def _on_failed(self, key: str, error: str) -> None:
        if key == self._task_key:
            self._busy = False
            self.status.setText(error)
            self._update_actions()

    def _on_cancelled(self, key: str) -> None:
        if key == self._task_key:
            self._busy = False
            self._show_config()

    def _copy_url(self) -> None:
        QApplication.clipboard().setText(self.url.text())

    def _open_guide(self) -> None:
        if self._documentation and self._documentation.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._documentation.resolve())))
