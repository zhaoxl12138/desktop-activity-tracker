"""Helpers for restarting DayLens after settings that require new runtime state."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import IO


@dataclass
class RestartHandle:
    """Control whether an already-created restart waiter may relaunch DayLens."""

    process: subprocess.Popen
    _stdin: IO[str]
    _signalled: bool = field(default=False, init=False)

    def _signal(self, action: str) -> None:
        if self._signalled:
            return
        self._stdin.write(f"{action}\n")
        self._stdin.flush()
        self._stdin.close()
        self._signalled = True

    def arm(self) -> None:
        self._signal("ARM")

    def cancel(self) -> None:
        try:
            self._signal("CANCEL")
        except Exception:
            terminate = getattr(self.process, "terminate", None)
            if terminate is not None:
                terminate()


def database_path_changed(current: str, requested: str) -> bool:
    """Return whether two database paths identify different Windows paths."""
    current_path = os.path.normcase(os.path.abspath(current))
    requested_path = os.path.normcase(os.path.abspath(requested))
    return current_path != requested_path


def current_launch_command() -> list[str]:
    """Return the command needed to launch the current DayLens entry point."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *sys.argv[1:]]
    return [sys.executable, os.path.abspath(sys.argv[0]), *sys.argv[1:]]


def schedule_restart(
    command: list[str],
    current_pid: int | None = None,
    *,
    deferred: bool = False,
) -> RestartHandle:
    """Create a hidden waiter and optionally arm it immediately."""
    if not command:
        raise ValueError("Restart command must not be empty")

    env = os.environ.copy()
    env["DAYLENS_RESTART_COMMAND"] = json.dumps(command, ensure_ascii=False)
    pid = current_pid or os.getpid()
    script = (
        "$action = [Console]::In.ReadLine(); "
        "if ($action -ne 'ARM') { exit 0 }; "
        "$launch = @(ConvertFrom-Json $env:DAYLENS_RESTART_COMMAND); "
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($launch.Count -gt 1) { "
        "Start-Process -FilePath ([string]$launch[0]) -ArgumentList @($launch[1..($launch.Count - 1)]) "
        "} else { Start-Process -FilePath ([string]$launch[0]) }"
    )
    process = subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-WindowStyle",
            "Hidden",
            "-Command",
            script,
        ],
        env=env,
        stdin=subprocess.PIPE,
        text=True,
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    if process.stdin is None:
        raise RuntimeError("Restart waiter did not expose its control pipe")
    handle = RestartHandle(process, process.stdin)
    if not deferred:
        handle.arm()
    return handle
