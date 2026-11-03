"""Local freshness is visible without regenerating AI or changing old reports."""
import os
import sqlite3
import threading
import time
from datetime import date
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from daylens import database, exporter
from daylens.gui.pages.reports import ReportsPage
from daylens.services.report_evidence_service import evidence_fingerprint, report_dates
from daylens.services.report_sections import attach_summary, summary_section


def _fixture(tmp_path, kind):
    db = str(tmp_path / "usage.db")
    conn = database.init_db(db)
    conn.execute("""INSERT INTO activity_sessions (
        session_id,start_time,end_time,date,process_name,normalized_title,
        category_key,category_name,duration_seconds,effective_seconds,
        engaged_seconds,passive_seconds,idle_seconds,metric_version,classification_version)
        VALUES ('s','2026-10-20 09:00:00','2026-10-20 09:10:00','2026-10-20',
        'app.exe','Activity','coding','编程开发',600,600,600,0,0,'attention-v1','rules-test')""")
    conn.commit()
    conn.close()
    day = {"daily": date(2026, 10, 20), "weekly": date(2026, 10, 25), "monthly": date(2026, 10, 31)}[kind]
    output = str(tmp_path / "reports" / kind)
    def generate():
        if kind == "daily":
            return exporter.export_markdown(db, day.isoformat(), output)
        if kind == "weekly":
            return exporter.export_weekly_report(db, 2026, 43, output)
        return exporter.export_monthly_report(db, 2026, 10, output)
    path = Path(generate())
    period = {"daily": "2026-10-20", "weekly": "2026-W43", "monthly": "2026-10"}[kind]
    attach_summary(path, "原有智能汇总，不应被覆盖。", {
        "kind": kind, "period": period,
        "evidence_fingerprint": evidence_fingerprint(db, kind, report_dates(kind, day)),
    })
    conn = sqlite3.connect(db)
    conn.execute("UPDATE activity_sessions SET category_key='gaming',category_name='游戏娱乐'")
    conn.commit()
    conn.close()
    return db, path, generate


@pytest.mark.parametrize("kind", ["daily", "weekly", "monthly"])
def test_native_regeneration_marks_stale_ai_without_replacing_its_section(tmp_path, monkeypatch, kind):
    from daylens.services.intelligence_client import DeepSeekProvider
    monkeypatch.setattr(DeepSeekProvider, "request_json", lambda *_a, **_k: pytest.fail("AI called"))
    _db, path, generate = _fixture(tmp_path, kind)
    old_section = summary_section(path.read_text(encoding="utf-8"))
    generate()
    content = path.read_text(encoding="utf-8")
    assert "AI 汇总基于旧数据" in content
    assert summary_section(content) == old_section
    generate()
    assert path.read_text(encoding="utf-8").count("daylens-ai-status:start") == 1


def _app():
    return QApplication.instance() or QApplication([])


def _until(app, predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.005)
    assert predicate()


def test_report_selection_exposes_stale_state_without_rewriting_file(tmp_path, monkeypatch):
    from daylens.services.intelligence_client import DeepSeekProvider
    monkeypatch.setattr(DeepSeekProvider, "request_json", lambda *_a, **_k: pytest.fail("AI called"))
    db, path, _generate = _fixture(tmp_path, "daily")
    original = path.read_bytes()
    app = _app()
    page = ReportsPage(db, str(tmp_path / "reports"))
    page.activate()
    page.tab_daily.selectRow(0)
    _until(app, lambda: "旧数据" in page.btn_open.toolTip())
    assert page.btn_open.isEnabled()
    assert path.read_bytes() == original
    page.close()


def test_freshness_controller_discards_old_selection_and_closed_results(tmp_path):
    from daylens.gui.report_freshness_controller import ReportFreshnessController
    app = _app()
    entered, release = threading.Event(), threading.Event()
    def load(path):
        if path == "old":
            entered.set()
            release.wait(2)
        return {"level": "stale", "message": path}
    controller = ReportFreshnessController("unused", tmp_path, loader=load)
    delivered = []
    controller.ready.connect(delivered.append)
    controller.request("old")
    assert entered.wait(1)
    controller.request("new")
    release.set()
    _until(app, lambda: len(delivered) == 1)
    assert delivered[0]["path"] == "new"
    controller.request("after-close")
    controller.close()
    for _ in range(20):
        app.processEvents()
        time.sleep(.005)
    assert len(delivered) == 1


def test_truncated_report_is_not_claimed_to_have_no_summary(tmp_path):
    from daylens.gui.report_freshness_controller import ReportFreshnessController
    app = _app()
    path = tmp_path / "large.md"
    path.write_text("x" * (2 * 1024 * 1024 + 1), encoding="utf-8")
    controller = ReportFreshnessController("unused", tmp_path)
    delivered = []
    controller.ready.connect(delivered.append)
    controller.request(path)
    _until(app, lambda: bool(delivered))
    assert delivered[0]["level"] == "unverifiable"
    controller.close()
