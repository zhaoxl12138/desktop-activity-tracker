from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from daylens.runtime import resolve_release_dir, resolve_release_exe_path  # noqa: E402


def test_release_dir_defaults_to_project_release():
    release_dir = resolve_release_dir(str(ROOT))
    assert release_dir == str(ROOT / "release")


def test_release_exe_path_points_to_release_daylens_exe():
    exe_path = resolve_release_exe_path(str(ROOT))
    assert exe_path == str(ROOT / "release" / "DayLens.exe")

