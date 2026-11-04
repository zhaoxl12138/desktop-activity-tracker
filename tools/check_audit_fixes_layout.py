"""Isolated layout captures for stale report feedback and long durations."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from PySide6.QtGui import QFont, QFontDatabase

from daylens.gui import style
from daylens.gui.pages.category_stats import _CategoryCard
from daylens.gui.pages.reports import ReportsPage
from tests.test_report_freshness import _app, _fixture, _until


def main():
    app = _app()
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    app.setFont(QFont("Microsoft YaHei", 10))
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    output = ROOT / "tmp" / "audit-fixes-layout" / str(scale)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="daylens-layout-audit-") as temp:
        db, _, _ = _fixture(Path(temp), "daily")
        for theme in ("dark", "light"):
            style.apply_theme(theme)
            app.setStyleSheet(style.get_global_style())
            for width, height in ((1280, 720), (1920, 1080)):
                target_width = max(520, int(width / scale) - 210)
                target_height = max(340, int(height / scale) - 120)
                page = ReportsPage(db, str(Path(temp) / "reports"))
                page.resize(target_width, target_height)
                page.show()
                page.tab_daily.selectRow(0)
                _until(app, lambda: page.freshness_label.text() == "AI 汇总已过期")
                assert page.freshness_label.isVisible()
                assert page.width() <= target_width and page.height() <= target_height
                label = page.freshness_label
                assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
                assert page.grab().save(str(output / f"{theme}-{width}x{height}-stale-report.png"))
                page.close()
                app.processEvents()

                seconds = 1200 * 3600 + 59 * 60
                card = _CategoryCard("work", "工作学习", seconds, seconds, style.COLORS["coding_green"])
                card.resize(target_width, 64)
                card.show()
                app.processEvents()
                label = card._time_lbl
                assert label.fontMetrics().horizontalAdvance(label.text()) <= label.contentsRect().width()
                assert card.grab().save(str(output / f"{theme}-{width}x{height}-long-duration.png"))
                card.close()
                app.processEvents()
    print(f"Stale report and long duration captures passed: {output}")


if __name__ == "__main__":
    main()
