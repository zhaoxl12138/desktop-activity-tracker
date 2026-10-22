"""Measure the goal workspace inside the actual MainWindow at physical targets."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication, QScrollArea

from test_gui_smoke import DummyWorker, MainWindow, _write_config, database


def main() -> None:
    app = QApplication.instance() or QApplication([])
    scale = float(os.getenv("QT_SCALE_FACTOR", "1"))
    output = Path(tempfile.gettempdir()) / "daylens-goal-layout-20261022"
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        config_path = root / "config.yaml"
        reports_dir = root / "reports"
        reports_dir.mkdir()
        config = _write_config(config_path)
        db_path = root / "usage.db"
        database.init_db(str(db_path)).close()
        worker = DummyWorker()
        window = MainWindow(str(root), config, str(db_path), str(config_path),
                            str(reports_dir), worker)
        if os.getenv("DAYLENS_TEST_LOWER_MIN") == "1":
            window.setMinimumSize(800, 450)
        for physical_width, physical_height in ((1280, 720), (1920, 1080)):
            requested_width = round(physical_width / scale)
            requested_height = round(physical_height / scale)
            window.resize(requested_width, requested_height)
            window.show()
            window.navigate_to("stats", tab="goals")
            app.processEvents()
            page = window.pages["goals"]
            for count in (0, 3):
                goals = [
                    {"id": f"g{i}", "type": "outcome", "title": f"目标 {i}",
                     "target_kind": None, "target_id": None, "target_minutes": None,
                     "confirmed": False, "confirmed_at": None}
                    for i in range(count)
                ]
                page.set_model({"day": page.selected_day(), "status": "ready",
                                "revision": 0, "goals": goals})
                app.processEvents()
                scroller = page.findChild(QScrollArea, "goalWorkspaceScroll")
                assert scroller is not None
                assert len(page.goal_cards) == count
                assert page.new_goal_button.isVisible()
                assert scroller.verticalScrollBar().maximum() >= 0
                target = output / (
                    f"embedded-{physical_width}x{physical_height}-"
                    f"{count}goals-{scale:g}"
                    f"{'-lower-min' if os.getenv('DAYLENS_TEST_LOWER_MIN') == '1' else ''}.png"
                )
                assert window.grab().save(str(target))
                print(
                    f"requested={requested_width}x{requested_height} logical "
                    f"actual={window.width()}x{window.height()} logical "
                    f"physical={round(window.width()*scale)}x{round(window.height()*scale)} "
                    f"goal_page={page.width()}x{page.height()} count={count} "
                    f"scroll_max={scroller.verticalScrollBar().maximum()}"
                )
        window.close()
        app.processEvents()


if __name__ == "__main__":
    main()
