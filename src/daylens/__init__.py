"""DayLens - Personal digital behavior analysis system."""

import os
import sys


def get_app_root():
    """Return the application root directory.

    In PyInstaller frozen mode, returns the directory containing the .exe.
    In normal Python, returns the project root (parent of this package).
    """
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # Navigate: __init__.py -> daylens/ -> src/ -> project_root/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
