"""Run the Daylog-managed iPhone Screen Time receiver on Windows."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import subprocess
import sys


@dataclass(frozen=True)
class ReceiverStatus:
    state: str
    url: str
    interface: str


def pairing_key_path() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "DayLens" / "iphone-screen-time" / "pairing-key.txt"
    return None


def manage_receiver(manager: Path, action: str) -> ReceiverStatus:
    if sys.platform != "win32":
        raise RuntimeError("接收端管理仅在 Windows 上可用。")
    if action not in {"Start", "Status"}:
        raise ValueError(f"Unsupported receiver action: {action}")
    if not manager.is_file():
        raise RuntimeError("找不到 Daylog 的接收端管理脚本，请先同步最新版 Daylog。")

    powershell = (
        Path(os.environ.get("SystemRoot", r"C:\Windows"))
        / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"
    )
    command = (
        '$ErrorActionPreference = "Stop"; '
        '[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); '
        '& $env:DAYLENS_PHONE_MANAGER -Action $env:DAYLENS_PHONE_ACTION | ConvertTo-Json -Compress'
    )
    try:
        result = subprocess.run(
            [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "RemoteSigned",
             "-Command", command],
            cwd=manager.parent,
            env={**os.environ, "DAYLENS_PHONE_MANAGER": str(manager), "DAYLENS_PHONE_ACTION": action},
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=50 if action == "Start" else 12,
        )
    except subprocess.TimeoutExpired as error:
        raise RuntimeError("等待接收端响应超时，请检查局域网后刷新状态。") from error
    except OSError as error:
        raise RuntimeError(f"无法运行接收端管理脚本。{error}") from error
    if result.returncode:
        detail = next((line.strip() for line in result.stderr.splitlines() if line.strip()), "")
        raise RuntimeError(f"接收端管理脚本执行失败。{detail}")
    try:
        status = json.loads(result.stdout)
        return ReceiverStatus(status["State"], status["URL"], status["Interface"])
    except (ValueError, KeyError, TypeError) as error:
        raise RuntimeError("无法读取接收端状态，请确认 Daylog 管理脚本版本。") from error
