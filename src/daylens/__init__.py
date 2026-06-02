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


def get_data_dir():
    """Return the persistent user-data directory (survives rebuilds).

    Frozen: data/ alongside the .exe release folder (project root).
    Normal Python: data/ under project root.
    """
    if getattr(sys, 'frozen', False):
        # _MEIPASS = release/_internal/ → release/ = parent → project root = grandparent
        return os.path.join(os.path.dirname(os.path.dirname(sys._MEIPASS)), "data")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
