from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_build_release_script_defines_release_as_publish_target():
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "DayLens.spec" in script
    assert "release" in script
    assert "DayLens.exe" in script


def test_build_release_script_publishes_from_staging_and_keeps_rollback():
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "release_staging" in script
    assert "release_previous" in script
    assert "os.replace" in script
    assert "--help" in script
    assert "taskkill" in script

