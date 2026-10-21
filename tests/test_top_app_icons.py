from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens.gui.pages.today_overview import TodayOverviewPage  # noqa: E402


def test_top_app_icon_prefers_builtin_png_without_com_shortcut_scan(monkeypatch):
    cached_png = r"D:\OfficeSoftware\DayLens\assets\icons\daylens.exe.png"

    monkeypatch.setattr(
        TodayOverviewPage,
        "_icon_png_path",
        staticmethod(lambda process_name_lower: cached_png),
    )

    page = TodayOverviewPage.__new__(TodayOverviewPage)

    assert page._resolve_icon_source("DayLens.exe") == cached_png


def test_today_overview_does_not_call_windows_com_for_top_app_icons():
    source = (SRC / "daylens" / "gui" / "pages" / "today_overview.py").read_text(
        encoding="utf-8"
    )
    assert "win32com.client" not in source


def test_top_app_uses_resolved_display_icon_process_for_codex():
    assert TodayOverviewPage._icon_process_for_display("WindowsTerminal.exe", "Codex") == "Codex.exe"
