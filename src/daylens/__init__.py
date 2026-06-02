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
        parent = os.path.dirname(exe_dir)
        grandparent = os.path.dirname(parent)

        # onedir build: project/dist/DayLens/DayLens.exe
        if (os.path.basename(parent).startswith("dist")
                and os.path.isfile(os.path.join(grandparent, "config", "config.yaml"))):
            return grandparent

        # onefile/local build: project/dist/DayLens.exe or project/dist2/DayLens.exe
        if (os.path.basename(exe_dir).startswith("dist")
                and os.path.isfile(os.path.join(parent, "config", "config.yaml"))):
            return parent

        return exe_dir
    # Navigate: __init__.py -> daylens/ -> src/ -> project_root/
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
