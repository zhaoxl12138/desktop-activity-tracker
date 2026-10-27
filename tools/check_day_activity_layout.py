"""Synthetic full-day detail layout captures; never opens a real database."""
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication
from daylens.gui import style
from daylens.gui.widgets.day_activity_dialog import DayActivityDialog
from daylens.services.day_activity_service import build_day_activity


def fixture(day, *, morning=False):
    rows = []
    items = [
        ("07:30", "07:45", "reading", "浏览器", "自考题库 · 章节练习", 0, 0),
        ("09:10", "10:15", "coding", "编辑器", "Camera Driver — 编程与调试", 0, 0),
        ("10:15", "10:45", "reading", "浏览器", "HAL3 Request / Result · 技术资料", 0, 0),
        ("10:45", "10:50", "social", "微信", "工作群讨论", 0, 0),
        ("10:50", "11:05", "reading", "浏览器", "学习资料 · " + "较长的中文标题" * 12, 0, 120),
        ("12:00", "12:20", "video", "视频播放器", "午间观看 · 视频节目", 1200, 0),
        ("13:15", "13:25", "finance", "同花顺", "市场行情", 0, 0),
        ("14:00", "14:02", "tools", "资源管理器", "项目文件", 0, 0),
        ("15:30", "16:30", "office", "文档编辑", "需求方案 · 文档整理", 0, 0),
        ("17:10", "17:40", "idle", "空闲", "已记录的空闲区间", 0, 1800),
        ("18:10", "18:20", "coding", "编辑器", "重叠证据 A", 0, 0),
        ("18:15", "18:30", "social", "微信", "重叠证据 B", 0, 0),
        ("20:30", "21:20", "video", "视频播放器", "晚间观看 · 视频节目", 3000, 0),
    ]
    if morning:
        items = [
            ("00:00", "09:30", "idle", "空闲", "开始活动前的空闲", 0, 34200),
            ("09:42", "09:52", "finance", "同花顺", "市场行情", 0, 120),
            ("10:01", "10:06", "reading", "浏览器", "技术学习", 0, 0),
            ("10:07", "10:18", "social", "微信", "工作群讨论", 0, 0),
            ("10:18", "10:20", "tools", "资源管理器", "项目文件", 0, 0),
            ("10:22", "10:27", "browser_general", "浏览器", "页面浏览", 0, 0),
            ("10:30", "10:33", "other", "其他应用", "其他活动", 0, 0),
            ("10:40", "10:55", "coding", "编辑器", "较长的中文标题" * 12, 0, 0),
            ("11:00", "11:15", "idle", "空闲", "中间空闲，不压缩", 0, 900),
            ("11:20", "11:30", "finance", "同花顺", "市场行情", 0, 60),
            ("12:11", "12:40", "video", "腾讯视频", "午间观看", 1740, 0),
            ("12:40", "14:00", "idle", "空闲", "末次活动后的空闲", 0, 4800),
        ]
    for index, (start, end, category, process, title, passive, idle) in enumerate(items):
        left = datetime.fromisoformat(day + " " + start)
        right = datetime.fromisoformat(day + " " + end)
        duration = int((right - left).total_seconds())
        rows.append({"session_id": str(index), "start_time": left.isoformat(sep=" "),
                     "end_time": right.isoformat(sep=" "), "date": day,
                     "process_name": process, "normalized_title": title,
                     "category_key": category, "category_name": {
                         "reading": "阅读学习", "coding": "技术学习 / 开发", "office": "办公 / 求职",
                         "video": "娱乐休闲", "social": "社交通讯", "finance": "投资理财",
                         "tools": "系统工具", "idle": "空闲", "browser_general": "浏览器", "other": "其他",
                     }[category], "metric_version": "attention-v1", "classification_version": "qa",
                     "duration_seconds": duration, "effective_seconds": duration - idle,
                     "engaged_seconds": duration - passive - idle, "passive_seconds": passive,
                     "idle_seconds": idle})
    return build_day_activity(rows, day, captured_at=datetime.fromisoformat(day + (" 14:00:00" if morning else " 22:40:00")))


def main():
    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont("C:/Windows/Fonts/msyh.ttc")
    app.setFont(QFont("Microsoft YaHei", 10))
    output = ROOT / "tmp" / "day-activity-fit-range-layout" / os.environ.get("QT_SCALE_FACTOR", "1")
    output.mkdir(parents=True, exist_ok=True)
    day = "2026-10-25"
    days = [(datetime.fromisoformat(day) - timedelta(days=offset)).date().isoformat()
            for offset in reversed(range(7))]
    scale = float(os.environ.get("QT_SCALE_FACTOR", "1"))
    for theme in ("dark", "light"):
        style.apply_theme(theme)
        for screen in ((1280, 720), (1920, 1080)):
            logical_width, logical_height = (int(value / scale) for value in screen)
            popup = min(1180, int(logical_width * .9)), min(900, int(logical_height * .9))
            for morning in (False, True):
                sample = fixture(day, morning=morning)
                dialog = DayActivityDialog("not-a-database", day, days,
                                           loader=lambda *_args, _sample=sample, **_kwargs: _sample)
                dialog.resize(*popup)
                dialog.show()
                deadline = time.monotonic() + 5
                while dialog.model.get("status") == "loading" and time.monotonic() < deadline:
                    app.processEvents()
                    time.sleep(.005)
                assert dialog.model["status"] == ("ready" if morning else "partial")
                assert dialog.model["totals"] == sample["totals"]
                assert not hasattr(dialog, "viewport")
                assert not hasattr(dialog, "overview")
                assert (dialog.timeline.range_start, dialog.timeline.range_end) == ((34200, 46800) if morning else (27000, 77400))
                assert dialog.events_model.rowCount() >= (7 if morning else 8)
                app.processEvents()
                assert dialog.timeline.width() < dialog.width()
                assert dialog.width() <= logical_width and dialog.height() <= logical_height
                assert dialog.timeline.width() <= dialog.scroll.viewport().width()
                labels = dialog.timeline.hour_labels()
                for (_, left, _), (_, right, _) in zip(labels, labels[1:]):
                    assert left.right()+2 <= right.left()
                path = output / f"{theme}-{screen[0]}x{screen[1]}-{'morning' if morning else 'long-day'}"
                assert dialog.grab().save(str(path) + "-categories.png")
                dialog.events_table.selectRow(0)
                # A new seven-lane model posts nested layout requests. Settle
                # those before scrolling; otherwise Qt can still have max=0.
                app.processEvents()
                dialog.scroll.ensureWidgetVisible(dialog.events_table)
                app.processEvents()
                assert dialog.events_table.viewport().height() >= 2 * dialog.events_table.verticalHeader().defaultSectionSize()
                table_top = dialog.events_table.mapTo(dialog.scroll.viewport(), dialog.events_table.rect().topLeft())
                assert table_top.y() >= 0
                assert table_top.y() < dialog.scroll.viewport().height(), {
                    "theme": theme, "screen": screen, "morning": morning,
                    "table_y": table_top.y(), "viewport_height": dialog.scroll.viewport().height(),
                    "scroll": dialog.scroll.verticalScrollBar().value(),
                    "maximum": dialog.scroll.verticalScrollBar().maximum(),
                }
                assert dialog.grab().save(str(path) + "-events.png")
                if "entertainment" in dialog.category_buttons:
                    original_summary = dialog.summary_label.text()
                    original_range = (dialog.timeline.range_start, dialog.timeline.range_end)
                    dialog.category_buttons["entertainment"].click()
                    app.processEvents()
                    assert [lane["key"] for lane in dialog.timeline.lanes] == ["entertainment"]
                    assert (dialog.timeline.range_start, dialog.timeline.range_end) == original_range
                    assert dialog.summary_label.text() == original_summary
                    dialog.scroll.verticalScrollBar().setValue(0)
                    app.processEvents()
                    assert dialog.grab().save(str(path) + "-filtered.png")
                dialog.close()
    print(f"Day activity layout captures passed: {output}")


if __name__ == "__main__":
    main()
