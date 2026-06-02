from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_daylens_spec_uses_onedir_build():
    spec = (ROOT / "DayLens.spec").read_text(encoding="utf-8")

    assert "stale_onefile_exe" in spec
    assert "DayLens.exe" in spec
    assert ".unlink()" in spec
    assert "exclude_binaries=True" in spec
    assert "COLLECT(" in spec
    assert "name='DayLens'" in spec
