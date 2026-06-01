"""Foreground window detection using pywin32 and psutil."""

import win32gui
import win32process
import psutil


def get_foreground_window_info():
    """Return dict with window_title, process_name, exe_path, pid, hwnd; or None on failure."""
    try:
        hwnd = win32gui.GetForegroundWindow()
        if not hwnd:
            return None

        window_title = win32gui.GetWindowText(hwnd)
        thread_id, pid = win32process.GetWindowThreadProcessId(hwnd)

        if not pid:
            return None

        # Unwrap the bizarre psutil pid from GetWindowThreadProcessId
        if isinstance(pid, tuple):
            pid = pid[-1] if pid[-1] else pid[0]
        pid = int(pid)

        try:
            proc = psutil.Process(pid)
            process_name = proc.name()
            exe_path = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            process_name = None
            exe_path = None

        return {
            "hwnd": hwnd,
            "window_title": window_title or "",
            "process_name": process_name or "",
            "exe_path": exe_path or "",
            "pid": pid,
        }
    except Exception:
        return None
