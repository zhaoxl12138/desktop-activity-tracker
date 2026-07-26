"""Process-wide lock shared by the GUI and CLI recording entry points."""

from __future__ import annotations

import ctypes
import os
from dataclasses import dataclass
from ctypes import wintypes


MUTEX_NAME = "Global\\DayLens_RecordingInstance"
ERROR_ALREADY_EXISTS = 183


@dataclass
class RecordingInstanceLock:
    """Owned OS mutex handle; keeping this object alive keeps the lock held."""

    handle: object | None

    def close(self) -> None:
        if self.handle is None:
            return
        ctypes.windll.kernel32.CloseHandle(self.handle)
        self.handle = None

    def __del__(self) -> None:
        self.close()


def acquire_recording_lock() -> tuple[bool, RecordingInstanceLock | None]:
    """Acquire the shared lock, returning ``False`` when another instance owns it."""
    if os.name != "nt":
        return True, RecordingInstanceLock(None)

    kernel32 = ctypes.windll.kernel32
    kernel32.CreateMutexW.argtypes = [
        wintypes.LPCVOID,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateMutexW.restype = wintypes.HANDLE
    handle = kernel32.CreateMutexW(None, True, MUTEX_NAME)
    if not handle:
        raise ctypes.WinError()
    if kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
        kernel32.CloseHandle(handle)
        return False, None

    lock = RecordingInstanceLock(handle)
    return True, lock
