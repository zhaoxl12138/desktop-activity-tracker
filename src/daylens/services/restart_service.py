"""Helpers for restarting DayLens after settings that require new runtime state."""

from __future__ import annotations

import json
import os
import subprocess
import sys


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


def schedule_restart(command: list[str], current_pid: int | None = None) -> None:
    """Start a hidden waiter that relaunches DayLens after this process exits."""
    if not command:
        raise ValueError("Restart command must not be empty")

    env = os.environ.copy()
    env["DAYLENS_RESTART_COMMAND"] = json.dumps(command, ensure_ascii=False)
    pid = current_pid or os.getpid()
    script = (
        "$launch = @(ConvertFrom-Json $env:DAYLENS_RESTART_COMMAND); "
        f"Wait-Process -Id {pid} -ErrorAction SilentlyContinue; "
        "if ($launch.Count -gt 1) { "
        "Start-Process -FilePath ([string]$launch[0]) -ArgumentList @($launch[1..($launch.Count - 1)]) "
        "} else { Start-Process -FilePath ([string]$launch[0]) }"
    )
    subprocess.Popen(
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
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
