"""Mouse/keyboard idle time detection via Windows GetLastInputInfo."""

import ctypes


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_uint),
        ("dwTime", ctypes.c_uint),
    ]


def get_idle_seconds():
    """Return seconds since last mouse or keyboard input. Uses system-wide idle timer."""
    lii = _LASTINPUTINFO()
    lii.cbSize = ctypes.sizeof(_LASTINPUTINFO)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 0.0
    tick_count = ctypes.windll.kernel32.GetTickCount()
    elapsed_ms = tick_count - lii.dwTime
    # Handle tick counter wraparound (~49.7 days)
    if elapsed_ms < 0:
        elapsed_ms = 0
    return elapsed_ms / 1000.0
