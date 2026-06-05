from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_uses_daylens_entrypoint_and_clean_description():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'desktop-activity-tracker = "daylens.main:main"' in text
    assert 'description = "Windows desktop activity tracking and analysis"' in text

