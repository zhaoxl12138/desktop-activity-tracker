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

    Existing frozen installs keep legacy state under the application root.
    New frozen installs use LocalAppData. Source runs keep project-local data.
    """
    app_root = get_app_root()
    state_names = ("usage.db", "user_config.yaml", "reports", "backups", "logs")
    # Source and frozen runs from a linked worktree must share the canonical
    # project state. This prevents a second database from being created merely
    # because development runs from .worktrees/<branch>.
    normalized_root = os.path.normcase(os.path.normpath(app_root))
    normalized_parts = normalized_root.split(os.sep)
    if ".worktrees" in normalized_parts:
        worktree_index = normalized_parts.index(".worktrees")
        original_parts = os.path.normpath(app_root).split(os.sep)
        workspace_root = os.sep.join(original_parts[:worktree_index]) or os.sep
        shared_data_dir = os.path.join(workspace_root, "data")
        if any(
            os.path.exists(os.path.join(shared_data_dir, name))
            for name in state_names
        ):
            return shared_data_dir
    if getattr(sys, 'frozen', False):
        legacy_dir = os.path.join(app_root, "data")
        if any(os.path.exists(os.path.join(legacy_dir, name)) for name in state_names):
            return legacy_dir
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            return os.path.join(local_app_data, "DayLens")
        return legacy_dir
    return os.path.join(app_root, "data")
