"""Desktop Activity Tracker - Windows desktop usage time recorder."""

import os
import sys


def get_app_root():
    """Return the application root directory.

    In PyInstaller frozen mode, returns the directory containing the .exe.
    In normal Python, returns the project root (parent of this package).
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Navigate: __init__.py -> desktop_activity_tracker/ -> src/ -> project_root/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
