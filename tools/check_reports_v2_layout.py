"""Synthetic report-center captures; never touches production data or AI."""

import os
import sys
import tempfile
import time
from pathlib import Path
from datetime import datetime, timedelta

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src")]

from PySide6.QtCore import QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from daylens import database, exporter
from daylens.gui import style
from daylens.gui.pages.reports import ReportsPage
from daylens.services.daily_goal_service import GoalStore
from daylens.session_tracker import ActivitySession


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    app.setFont(QFont("Microsoft YaHei", 10))
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    output = ROOT / "tmp" / "report-v2-layout" / str(scale)
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as directory:
        temp = Path(directory)
        db = temp / "usage.db"
        conn = database.init_db(str(db))
        start = datetime(2026, 10, 20, 9)
        for i in range(8):
            a = start + timedelta(minutes=30 * i)
            database.insert_session(
                conn,
                ActivitySession(
                    f"s{i}",
                    a,
                    a + timedelta(minutes=20),
                    "2026-10-20",
                    "Obsidian.exe",
                    "C:/Obsidian.exe",
                    "阅读嵌入式驱动笔记与技术文档 · 长中文标题布局验证",
                    "阅读嵌入式驱动笔记与技术文档 · 长中文标题布局验证",
                    "reading",
                    "阅读学习",
                    "interactive_required",
                    duration_seconds=1200,
                    effective_seconds=1000,
                    engaged_seconds=1000,
                    idle_seconds=200,
                    classification_version="rules-test",
                ),
            )
        database.close_db(conn)
        GoalStore(temp / "intelligence").save_day(
            "2026-10-20",
            [
                {
                    "id": "g1",
                    "type": "time_commitment",
                    "title": "阅读嵌入式驱动资料并整理一份技术笔记",
                    "target_kind": "category",
                    "target_id": "work",
                    "target_minutes": 150,
                    "confirmed": False,
                    "confirmed_at": None,
                }
            ],
            expected_revision=0,
        )
        reports = temp / "reports"
        exporter.export_markdown(str(db), "2026-10-20", str(reports / "daily"))
        for theme in ("dark", "light"):
            style.apply_theme(theme)
            app.setStyleSheet(style.get_global_style())
            for width, height in ((1280, 720), (1920, 1080)):
                page = ReportsPage(str(db), str(reports))
                # Reserve the real shell's sidebar and header in logical px.
                target_width = max(520, int(width / scale) - 210)
                target_height = max(340, int(height / scale) - 120)
                page.resize(target_width, target_height)
                page.show()
                app.processEvents()
                page.tab_daily.selectRow(0)
                deadline = time.monotonic() + 4
                while (
                    "关键发现" not in page.preview.browser.toPlainText()
                    and time.monotonic() < deadline
                ):
                    app.processEvents()
                    time.sleep(0.01)
                assert "关键发现" in page.preview.browser.toPlainText()
                assert "daylens-report" not in page.preview.browser.toPlainText()
                assert page.width() <= target_width, (page.size(), target_width)
                assert page.height() <= target_height, (page.size(), target_height)
                for widget in (
                    page.btn_daily,
                    page.btn_monthly,
                    page.preview.browser,
                    page.btn_sync_selected,
                ):
                    point = widget.mapTo(page, QPoint(widget.width(), widget.height()))
                    assert point.x() <= page.width() and point.y() <= page.height(), (
                        widget.text() if hasattr(widget, "text") else "browser",
                        point,
                        page.size(),
                    )
                assert page.preview.browser.height() >= 70
                assert page.grab().save(str(output / f"{theme}-{width}x{height}.png"))
                page.close()
                app.processEvents()
    print(f"Report V2 layout passed: {output}")


if __name__ == "__main__":
    main()
