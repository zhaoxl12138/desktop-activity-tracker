"""Render isolated goal states and assert bounded geometry at common DPI scales."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QTableWidget

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from daylens.gui import style as ui_style  # noqa: E402
from daylens.gui.pages.daily_goals import DailyGoalsPage  # noqa: E402


def _goals(count: int) -> list[dict]:
    values = [
        {"id": "t1", "type": "time_commitment", "title": "学习 Camera 驱动",
         "target_kind": "category", "target_id": "reading", "target_minutes": 120,
         "actual_seconds": 4500, "difference_seconds": 2700,
         "evidence_status": "ready", "confirmed": False, "confirmed_at": None},
        {"id": "o1", "type": "outcome", "title": "完成 V4L2 学习笔记",
         "target_kind": None, "target_id": None, "target_minutes": None,
         "confirmed": False, "confirmed_at": None},
        {"id": "t2", "type": "time_commitment", "title": "编码练习",
         "target_kind": "category", "target_id": "coding", "target_minutes": 60,
         "actual_seconds": None, "difference_seconds": None,
         "evidence_status": "insufficient_data", "confirmed": False, "confirmed_at": None},
    ]
    return values[:count]


def main() -> None:
    app = QApplication.instance() or QApplication([])
    output = Path(tempfile.gettempdir()) / "daylens-goal-layout-20261022"
    output.mkdir(exist_ok=True)
    scale = os.getenv("QT_SCALE_FACTOR", "1")
    for theme in ("dark", "light"):
        ui_style.apply_theme(theme)
        for width, height in ((1280, 720), (1366, 768), (1920, 1080)):
            for count in (0, 1, 3):
                with tempfile.TemporaryDirectory() as directory:
                    page = DailyGoalsPage(directory)
                    page.resize(round(width / float(scale)), round(height / float(scale)))
                    page.set_model({"day": page.selected_day(), "status": "ready",
                                    "revision": 1, "goals": _goals(count)})
                    page.show()
                    app.processEvents()
                    assert page.findChildren(QTableWidget) == []
                    assert page.new_goal_button.width() >= 90
                    assert page.day_picker.width() >= 110
                    assert page.empty_state.height() <= 300
                    assert page.empty_state.isVisible() == (count == 0)
                    assert len(page.goal_cards) == count
                    assert all(card.width() <= 720 and card.width() >= 340
                               for card in page.goal_cards)
                    if count == 3:
                        assert page.goal_cards[0].geometry().intersected(
                            page.goal_cards[1].geometry()).isEmpty()
                        assert page.goal_cards[2].y() > page.goal_cards[0].y()
                    target = output / f"{theme}-{width}x{height}-{count}goals-{scale}.png"
                    assert page.grab().save(str(target))
                    print(f"OK {theme} {width}x{height} {count} goals scale {scale} -> {target}")
                    page.close()
                    app.processEvents()


if __name__ == "__main__":
    main()
