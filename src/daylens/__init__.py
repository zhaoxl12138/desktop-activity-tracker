"""DayLens - Personal digital behavior analysis system."""

import os
import sys


def get_app_root():
    """Return the application root directory.

    Frozen build:
    - If an ancestor of the executable contains config/config.yaml, treat that
      ancestor as the project root.
    - Otherwise fall back to the executable directory.

    Normal Python: project root (parent of this package).
    """
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        candidates = [
            exe_dir,
            os.path.dirname(exe_dir),
            os.path.dirname(os.path.dirname(exe_dir)),
        ]
        for candidate in candidates:
            if os.path.isfile(os.path.join(candidate, "config", "config.yaml")):
                return candidate
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_data_dir():
    """Return the persistent user-data directory (survives rebuilds).

    Frozen build: data/ under the resolved app root.
    Normal Python: data/ under project root (3 levels up from this file).
    """
    if getattr(sys, 'frozen', False):
        return os.path.join(get_app_root(), "data")
    return os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
