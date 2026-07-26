from __future__ import annotations

from pathlib import Path


def test_shortcut_script_does_not_embed_personal_absolute_paths():
    source = Path("tools/fix_shortcut.ps1").read_text(encoding="utf-8")

    assert "Administrator" not in source
    assert "D:\\OfficeSoftware\\DayLens" not in source
    assert "$PSScriptRoot" in source
