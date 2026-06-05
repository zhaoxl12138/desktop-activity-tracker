from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens.gui.pages.today_overview import TodayOverviewPage  # noqa: E402


def test_top_app_icon_prefers_desktop_shortcut_icon(monkeypatch):
    shortcut_icon = r"D:\OfficeSoftware\DayLens\release\DayLens.exe"
    cached_png = r"D:\OfficeSoftware\DayLens\assets\icons\daylens.exe.png"

    monkeypatch.setattr(
        TodayOverviewPage,
        "_desktop_shortcut_icon_path",
        staticmethod(lambda process_name: shortcut_icon if process_name == "DayLens.exe" else None),
    )
    monkeypatch.setattr(
        TodayOverviewPage,
        "_icon_png_path",
        staticmethod(lambda process_name_lower: cached_png),
    )

    page = TodayOverviewPage.__new__(TodayOverviewPage)

    assert page._resolve_icon_source("DayLens.exe") == shortcut_icon


def test_desktop_shortcut_icon_location_strips_resource_index():
    assert (
        TodayOverviewPage._parse_icon_location(r"D:\OfficeSoftware\DayLens\release\DayLens.exe,0")
        == r"D:\OfficeSoftware\DayLens\release\DayLens.exe"
    )


def test_top_app_uses_resolved_display_icon_process_for_codex():
    assert TodayOverviewPage._icon_process_for_display("WindowsTerminal.exe", "Codex") == "Codex.exe"
