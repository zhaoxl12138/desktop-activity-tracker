"""Capture isolated settings and rhythm layouts without reading the user's data."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QScrollArea

from daylens.gui import style
from daylens.gui.pages.settings import SettingsPage
from daylens.gui.widgets.dashboard_widgets import _RhythmCanvas, _TrendCanvas


def main() -> None:
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    app.setFont(QFont("Microsoft YaHei", 10))
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    output = ROOT / "tmp" / "settings-rhythm-layout" / f"{scale:g}"
    output.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        config = {
            "db_path": str(temp / "usage.db"),
            "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
        }
        with (patch("daylens.services.settings_service.load_page_config", return_value=config),
              patch("daylens.gui.widgets.intelligence_settings.credentials.read_key", return_value=None)):
            for theme in ("dark", "light"):
                style.apply_theme(theme)
                app.setStyleSheet(style.get_global_style() + style.get_input_style())
                for physical_width, physical_height in ((1280, 720), (1920, 1080)):
                    width = round(physical_width / scale)
                    height = round(physical_height / scale)
                    page = SettingsPage(str(temp / "config.yaml"), str(temp / "usage.db"),
                                        str(temp / "reports"))
                    page.resize(width, height)
                    page.show()
                    app.processEvents()
                    assert page.grab().save(str(output / f"{theme}-{physical_width}x{physical_height}-top.png"))
                    scroll = page.findChild(QScrollArea)
                    scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
                    app.processEvents()
                    assert page.grab().save(str(output / f"{theme}-{physical_width}x{physical_height}-bottom.png"))
                    page.close()

                rhythm = _RhythmCanvas()
                rhythm.resize(round(700 / scale), round(220 / scale))
                rhythm.set_data({"kind": "cumulative", "current": [i * 60 for i in range(48)],
                                 "labels": [f"{i//2:02d}:{i%2*30:02d}" for i in range(48)]})
                rhythm.show()
                app.processEvents()
                assert rhythm.grab().save(str(output / f"{theme}-rhythm.png"))
                rhythm.close()

                trend = _TrendCanvas()
                trend.resize(round(700 / scale), round(220 / scale))
                trend.set_series([float(i % 8) for i in range(24)], mode="today",
                                 work_points=[float(i % 8) for i in range(24)],
                                 entertainment_points=[float((i + 3) % 5) for i in range(24)])
                trend.show()
                app.processEvents()
                assert trend.grab().save(str(output / f"{theme}-trend.png"))
                trend.close()

    print(f"Settings/rhythm captures passed: {output}")


if __name__ == "__main__":
    main()
