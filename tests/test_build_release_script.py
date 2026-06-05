from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_release_script_defines_release_as_publish_target():
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "DayLens.spec" in script
    assert "release" in script
    assert "DayLens.exe" in script

