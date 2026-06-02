"""DayLens - Personal digital behavior analysis system."""

import os
import sys


def get_app_root():
    """Return the application root directory.

    In PyInstaller frozen mode, returns the directory containing the .exe,
    unless the exe is inside a build-output subdirectory (dist, dist2, etc.)
    and the parent has config/config.yaml — in that case use the parent so
    data survives clean rebuilds.

    In normal Python, returns the project root (parent of this package).
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        # If exe is in a dist-like directory, check parent for config/data
        parent = os.path.dirname(exe_dir)
        if (os.path.basename(exe_dir).startswith("dist")
                and os.path.isdir(os.path.join(parent, "config"))):
            return parent
        return exe_dir
    # Navigate: __init__.py -> daylens/ -> src/ -> project_root/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
