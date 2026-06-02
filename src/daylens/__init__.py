"""DayLens - Personal digital behavior analysis system."""

import os
import sys


def get_app_root():
    """Return the application root directory.

    Frozen: use sys._MEIPASS (PyInstaller's runtime extraction directory).
    For onedir builds this is the _internal/ folder alongside the .exe,
    which contains config/, assets/, and Python runtime.

    Normal Python: project root (parent of this package).
    """
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
