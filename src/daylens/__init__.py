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

    Frozen onedir: exe is in dist/DayLens/, _internal/ alongside → project root is 2 levels up.
    Frozen onefile: exe is at project root, no _internal/ → data/ alongside exe.
    Normal Python: data/ under project root (3 levels up from this file).
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if os.path.isdir(os.path.join(exe_dir, "_internal")):
            # onedir: dist/DayLens/ → project root = grandparent
            return os.path.join(os.path.dirname(os.path.dirname(exe_dir)), "data")
        # onefile: data/ alongside exe
        return os.path.join(exe_dir, "data")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
