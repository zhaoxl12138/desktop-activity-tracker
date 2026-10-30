"""Measure report/preview on 10,000 synthetic sessions in a temporary DB."""

import sys
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from daylens import database
from daylens.services.report_v2_service import build_context
from daylens.services.report_v2_renderer import render_report
from daylens.services.report_preview_service import PreviewCache
from daylens.gui.widgets.report_preview import ReportPreview


def main():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        db = root / "usage.db"
        conn = database.init_db(str(db))
        start = datetime(2026, 10, 20)
        rows = []
        for i in range(10000):
            a = start + timedelta(seconds=i * 5)
            rows.append(
                (
                    f"s{i}",
                    str(a),
                    str(a + timedelta(seconds=5)),
                    "2026-10-20",
                    "code.exe",
                    f"编辑文件-{i}",
                    "coding",
                    "编程开发",
                    5,
                    5,
                    5,
                    0,
                    0,
                    "attention-v1",
                    "rules-test",
                )
            )
        conn.executemany(
            """INSERT INTO activity_sessions(session_id,start_time,end_time,date,process_name,
            normalized_title,category_key,category_name,duration_seconds,effective_seconds,
            engaged_seconds,passive_seconds,idle_seconds,metric_version,classification_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            rows,
        )
        conn.commit()
        conn.close()
        started = time.perf_counter()
        model = build_context(
            str(db), "daily", ["2026-10-20"], now=datetime(2026, 10, 21)
        )
        query = time.perf_counter() - started
        started = time.perf_counter()
        content = render_report(model)
        render = time.perf_counter() - started
        assert model["stats"]["totals"]["effective_seconds"] == 50000
        report = root / "large.md"
        report.write_text(content, encoding="utf-8")
        cache = PreviewCache(root)
        started = time.perf_counter()
        payload = cache.load(report)
        cold = time.perf_counter() - started
        started = time.perf_counter()
        cache.load(report)
        warm = time.perf_counter() - started
        assert payload["truncated"]
        app = QApplication.instance() or QApplication([])
        widget = ReportPreview(str(root))
        original = widget.cache.load

        def slow(path):
            time.sleep(0.4)
            return original(path)

        widget.cache.load = slow
        ticks = []
        timer = QTimer()
        timer.setInterval(50)
        timer.timeout.connect(lambda: ticks.append(1))
        timer.start()
        widget.load_report(str(report))
        deadline = time.monotonic() + 5
        while not widget.browser.toPlainText() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        assert len(ticks) >= 5 and widget.browser.toPlainText()
        timer.stop()
        widget.close()
        print(
            f"10000 sessions: snapshot={query:.3f}s render={render:.3f}s cold-preview={cold:.4f}s warm-preview={warm:.4f}s; bytes={len(content.encode())}; GUI heartbeat={len(ticks)}; source total=50000 seconds"
        )


if __name__ == "__main__":
    main()
