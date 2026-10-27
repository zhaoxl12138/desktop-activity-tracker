"""Isolated work-rhythm screenshots, including the 10/26 rightmost column."""
import os
import sys
from datetime import date, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from daylens.gui import style
from daylens.gui.widgets.dashboard_widgets import RhythmComparisonCard
from daylens.utils import fmt_seconds


def sample():
    dates = [(date(2026, 10, 26)-timedelta(days=i)).isoformat() for i in reversed(range(7))]
    values = [6000, 0, None, 12960, 11700, 720, 300]
    total = sum(v for v in values if v is not None)
    return {
        "7d": {"title": "近7天工作节奏", "date_range": [dates[0], dates[-1]],
               "status": {"kind": "break", "label": "口径已变化"}, "conclusion": "10/20–10/26",
               "chart": {"kind": "bars", "dates": dates,
                         "labels": [f"10/{20+i}" for i in range(7)], "values": values},
               "metrics": [{"label": "日均参与", "value": fmt_seconds(total//6), "delta": ""},
                           {"label": "最高一天", "value": "10/23 周五", "delta": "3小时36分钟"},
                           {"label": "总时间", "value": fmt_seconds(total), "delta": ""}]},
        "today": {"title": "今日工作节奏", "conclusion": "截至14:00，工作参与1小时",
                  "chart": {"kind": "cumulative", "labels": [f"{i//2:02d}:{i%2*30:02d}" for i in range(48)],
                            "current": [i*120 for i in range(29)]+[None]*19}, "metrics": []},
        "30d": {"title": "近30天工作节奏", "conclusion": "9/27–10/26",
                "chart": {"kind": "bars", "values": [i*300 for i in range(30)],
                          "labels": [(date(2026, 10, 26)-timedelta(days=29-i)).strftime("%m/%d") for i in range(30)]},
                "metrics": []},
    }


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    app.setFont(QFont("Microsoft YaHei", 10))
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    output = ROOT / "tmp" / "rhythm-card-layout" / str(scale)
    output.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        style.apply_theme(theme)
        for screen in ((1280, 720), (1920, 1080)):
            width = min(700, int(screen[0]/scale*.55))
            for mode in ("7d", "today", "30d"):
                card = RhythmComparisonCard()
                card.set_data(sample())
                card.set_mode(mode)
                card.resize(width, 285)
                card.show()
                app.processEvents()
                assert card.width() <= int(screen[0]/scale)
                canvas = card.canvas
                assert canvas.height() >= 110
                canvas_bottom = canvas.mapTo(card, QPoint(0, canvas.height())).y()
                metrics_top = card._metric_labels[0][0].parentWidget().mapTo(card, QPoint(0, 0)).y()
                assert canvas_bottom < metrics_top
                if mode == "7d":
                    assert canvas._today_index() == 6
                    assert canvas._bar_hit_rects[1].height() >= 2
                    assert canvas._bar_hit_rects[2] is None
                    assert card.canvas._data["values"][-1] == 300
                    for i, bar in enumerate(canvas._bar_hit_rects):
                        if bar is not None:
                            assert abs(bar.center().x()-canvas._bar_slot(i, canvas._chart_rect()).center().x()) < .01
                assert card.grab().save(str(output / f"{theme}-{screen[0]}x{screen[1]}-{mode}.png"))
                card.close()
    print(f"Rhythm card layout captures passed: {output}")


if __name__ == "__main__":
    main()
