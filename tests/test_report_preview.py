from pathlib import Path
import time
import json
import hashlib

import pytest
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import QApplication


def test_preview_cache_reads_once_and_invalidates_by_file_identity(
    tmp_path, monkeypatch
):
    from daylens.services.report_preview_service import PreviewCache

    path = tmp_path / "one.md"
    path.write_text("# 报告\n正文", encoding="utf-8")
    calls = []
    original = Path.open

    def opened(self, *args, **kwargs):
        calls.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "open", opened)
    cache = PreviewCache(tmp_path)
    first = cache.load(path)
    second = cache.load(path)
    assert first["text"] == second["text"] == "# 报告\n正文"
    assert len(calls) == 1
    path.write_text("# 新报告\n新内容", encoding="utf-8")
    assert cache.load(path)["text"] == "# 新报告\n新内容"


def test_preview_cache_is_bounded_and_large_reports_degrade(tmp_path):
    from daylens.services.report_preview_service import PreviewCache

    cache = PreviewCache(tmp_path, max_entries=2, max_bytes=64)
    for i in range(5):
        path = tmp_path / f"{i}.md"
        path.write_text("# 标题\n一段正文", encoding="utf-8")
        cache.load(path)
    assert cache.entry_count <= 2 and cache.byte_count <= 64
    large = tmp_path / "large.md"
    large.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    loaded = cache.load(large)
    assert loaded["truncated"] is True
    assert len(loaded["text"]) <= 128 * 1024
    assert large.stat().st_size == 2 * 1024 * 1024 + 1
    dense = tmp_path / "dense.md"
    dense.write_text("| a | b |\n" * 1300, encoding="utf-8")
    assert cache.load(dense)["truncated"] is True


def test_preview_rejects_outside_root_and_invalid_encoding(tmp_path):
    from daylens.services.report_preview_service import PreviewCache

    cache = PreviewCache(tmp_path / "reports")
    outside = tmp_path / "private.md"
    outside.write_text("secret", encoding="utf-8")
    with pytest.raises(ValueError):
        cache.load(outside)
    root = tmp_path / "reports"
    root.mkdir()
    path = root / "broken.md"
    path.write_bytes(b"\xff\xfeBAD")
    with pytest.raises(UnicodeError):
        cache.load(path)


def wait_until(app, predicate):
    deadline = time.monotonic() + 4
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert predicate()


def test_preview_renders_markdown_toc_and_search_and_blocks_resources(tmp_path):
    from daylens.gui.widgets.report_preview import ReportPreview

    app = QApplication.instance() or QApplication([])
    path = tmp_path / "one.md"
    path.write_text(
        '# 报告\n<!-- daylens-report:{"kind":"daily"} -->\n## 分类统计\n学习内容\n## 分类统计\n第二部分\n'
        '![remote](https://example.com/a.png)\n<img src="file:///C:/secret">',
        encoding="utf-8",
    )
    widget = ReportPreview(str(tmp_path))
    widget.load_report(str(path))
    wait_until(app, lambda: "学习内容" in widget.browser.toPlainText())
    assert widget.toc.count() == 3
    assert "daylens-report" not in widget.browser.toPlainText()
    assert widget.toc.itemData(1) != widget.toc.itemData(2)
    widget.search.setText("第二部分")
    widget.find_next()
    assert widget.browser.textCursor().selectedText() == "第二部分"
    assert not widget.browser.openLinks()
    assert not widget.browser.openExternalLinks()
    assert not widget.browser.loadResource(2, QUrl("file:///C:/secret"))
    assert not widget.browser.loadResource(2, QUrl("https://example.com/a.png"))
    widget.close()


def test_preview_latest_selection_wins_and_clear_discards_results(tmp_path):
    from daylens.gui.widgets.report_preview import ReportPreview

    app = QApplication.instance() or QApplication([])
    widget = ReportPreview(str(tmp_path))
    for i in range(3):
        path = tmp_path / f"{i}.md"
        path.write_text(f"# report {i}", encoding="utf-8")
        widget.load_report(str(path))
    wait_until(app, lambda: "report 2" in widget.browser.toPlainText())
    widget.load_report(str(path))
    widget.clear("已选择多份报告")
    for _ in range(10):
        app.processEvents()
    assert widget.browser.toPlainText() == "已选择多份报告"
    widget.close()


def test_summary_status_is_read_only_and_unknown_for_legacy_appendix(
    tmp_path, monkeypatch
):
    from daylens.services.report_preview_service import summary_status
    from daylens.services.report_sections import START, END
    from daylens.services import intelligence_report_service

    monkeypatch.setattr(
        intelligence_report_service,
        "generate_budget_review",
        lambda *_a, **_k: pytest.fail("preview must not generate"),
    )
    assert summary_status("missing.db", "no appendix") == "未附加 AI 汇总"
    assert "无法验证" in summary_status("missing.db", START + "\nOLD\n" + END)


def test_document_appears_before_slow_evidence_check_finishes(tmp_path, monkeypatch):
    import threading
    from daylens.gui.widgets import report_preview

    app = QApplication.instance() or QApplication([])
    release = threading.Event()
    monkeypatch.setattr(
        report_preview, "summary_status", lambda *_a: (release.wait(3), "核验完成")[1]
    )
    path = tmp_path / "read.md"
    path.write_text("# 正文先出现", encoding="utf-8")
    widget = report_preview.ReportPreview(str(tmp_path))
    widget.load_report(str(path))
    deadline = time.monotonic() + 1
    while not widget.browser.toPlainText() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    try:
        assert "正文先出现" in widget.browser.toPlainText()
    finally:
        release.set()
        widget.close()


def test_new_summary_binds_actual_appendix_and_marks_changed_evidence(tmp_path):
    from daylens import database
    from daylens.services.report_sections import attach_summary
    from daylens.services.report_preview_service import summary_status
    from daylens.services.report_evidence_service import evidence_fingerprint

    db = tmp_path / "usage.db"
    database.init_db(str(db)).close()
    report = tmp_path / "report.md"
    report.write_text("# 原生报告", encoding="utf-8")
    fingerprint = evidence_fingerprint(str(db), "daily", ["2026-10-20"])
    attach_summary(
        report,
        "原汇总",
        {
            "kind": "daily",
            "period": "2026-10-20",
            "evidence_fingerprint": fingerprint,
            "facts": [],
            "facts_version": "review-facts-v1",
            "prompt_hash": hashlib.sha256(
                __import__(
                    "daylens.services.intelligence_reviews", fromlist=["REVIEW_PROMPT"]
                ).REVIEW_PROMPT.encode()
            ).hexdigest(),
            "privacy_revision": __import__(
                "daylens.services.intelligence_privacy", fromlist=["privacy_revision"]
            ).privacy_revision({}),
        },
    )
    content = report.read_text(encoding="utf-8")
    assert summary_status(str(db), content) == "AI 汇总证据一致"
    assert "无法验证" in summary_status(
        str(db), content.replace("原汇总", "改过的汇总")
    )
    import sqlite3

    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO activity_logs(timestamp,date,duration_seconds) VALUES ('2026-10-20 09:00:00','2026-10-20',60)"
        )
    assert "旧数据" in summary_status(str(db), content)


def test_summary_read_failure_is_unknown_not_latest(tmp_path):
    from daylens.services.report_sections import attach_summary
    from daylens.services.report_preview_service import summary_status

    report = tmp_path / "report.md"
    report.write_text("# 原报告", encoding="utf-8")
    attach_summary(
        report,
        "AI",
        {"kind": "daily", "period": "2026-10-20", "evidence_fingerprint": "old"},
    )
    assert "无法验证" in summary_status(
        "missing.db", report.read_text(encoding="utf-8")
    )


def test_parent_summary_marks_changed_child_stale(tmp_path):
    from daylens import database
    from daylens.services.report_sections import attach_summary
    from daylens.services.report_preview_service import summary_status
    from daylens.services.report_evidence_service import evidence_fingerprint

    db = tmp_path / "usage.db"
    database.init_db(str(db)).close()
    reviews = tmp_path / "intelligence" / "reviews"
    reviews.mkdir(parents=True)
    source = {
        "status": "ready",
        "evidence_fingerprint": "source-fingerprint",
        "observations": [],
    }
    child = reviews / "daily-2026-10-20.json"
    child.write_text(json.dumps(source), encoding="utf-8")
    report = tmp_path / "parent.md"
    report.write_text("# 周报", encoding="utf-8")
    evidence = {
        "kind": "weekly",
        "period": "2026-W43",
        "evidence_fingerprint": evidence_fingerprint(
            str(db), "weekly", [f"2026-10-{d}" for d in range(19, 26)]
        ),
        "source_reviews": [
            {
                "name": "daily-2026-10-20.json",
                "digest": hashlib.sha256(
                    json.dumps(source, ensure_ascii=False, sort_keys=True).encode()
                ).hexdigest(),
            }
        ],
    }
    attach_summary(report, "父级汇总", evidence)
    source["observations"] = [{"text": "已变化"}]
    child.write_text(json.dumps(source), encoding="utf-8")
    assert "旧数据" in summary_status(str(db), report.read_text(encoding="utf-8"))


def test_month_summary_checks_nested_daily_dependencies(tmp_path):
    from daylens import database
    from daylens.services.report_sections import attach_summary
    from daylens.services.report_preview_service import summary_status
    from daylens.services.report_evidence_service import evidence_fingerprint

    db = tmp_path / "usage.db"
    database.init_db(str(db)).close()
    root = tmp_path / "intelligence" / "reviews"
    root.mkdir(parents=True)

    def digest(value):
        return hashlib.sha256(
            json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()

    daily = {
        "status": "ready",
        "evidence_fingerprint": evidence_fingerprint(str(db), "daily", ["2026-10-20"]),
    }
    child = root / "daily-2026-10-20.json"
    child.write_text(json.dumps(daily), encoding="utf-8")
    weekly = {
        "status": "ready",
        "evidence_fingerprint": evidence_fingerprint(
            str(db), "weekly", [f"2026-10-{d}" for d in range(19, 26)]
        ),
        "source_reviews": [{"name": child.name, "digest": digest(daily)}],
    }
    middle = root / "weekly-2026-W43.json"
    middle.write_text(json.dumps(weekly), encoding="utf-8")
    report = tmp_path / "monthly.md"
    report.write_text("# 月报", encoding="utf-8")
    attach_summary(
        report,
        "月汇总",
        {
            "kind": "monthly",
            "period": "2026-10",
            "evidence_fingerprint": evidence_fingerprint(
                str(db), "monthly", [f"2026-10-{d:02}" for d in range(1, 32)]
            ),
            "source_reviews": [{"name": middle.name, "digest": digest(weekly)}],
        },
    )
    daily["observations"] = ["变化"]
    child.write_text(json.dumps(daily), encoding="utf-8")
    assert "旧数据" in summary_status(str(db), report.read_text(encoding="utf-8"))


def test_source_identity_is_not_bound_to_changed_excerpt(tmp_path):
    from daylens.services.intelligence_report_service import capture_review_sources

    source = {"observations": [{"text": "新摘要"}], "topics": []}
    (tmp_path / "daily-2026-10-20.json").write_text(
        json.dumps(source), encoding="utf-8"
    )
    old = {
        "id": "daily:2026-10-20",
        "period": "2026-10-20",
        "observations": [{"text": "旧摘要"}],
        "topics": [],
    }
    assert capture_review_sources(tmp_path, [old]) == []
    old["observations"] = [{"text": "新摘要"}]
    assert len(capture_review_sources(tmp_path, [old])) == 1
    assert capture_review_sources(tmp_path, [old, {"id": "daily:2026-10-21"}]) == []


def test_slow_old_status_does_not_hold_new_document_read(tmp_path, monkeypatch):
    import threading
    from daylens.gui.widgets import report_preview

    app = QApplication.instance() or QApplication([])
    release = threading.Event()
    monkeypatch.setattr(
        report_preview, "summary_status", lambda *_a: (release.wait(3), "核验")[1]
    )
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_text("# A正文", encoding="utf-8")
    b.write_text("# B正文", encoding="utf-8")
    widget = report_preview.ReportPreview(str(tmp_path))
    widget.load_report(str(a))
    wait_until(app, lambda: "A正文" in widget.browser.toPlainText())
    widget.load_report(str(b))
    deadline = time.monotonic() + 1
    while "B正文" not in widget.browser.toPlainText() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    try:
        assert "B正文" in widget.browser.toPlainText()
    finally:
        release.set()
        widget.close()


def test_native_goal_state_changes_are_detected_without_rewriting_report(tmp_path):
    from daylens import database, exporter
    from daylens.services.daily_goal_service import GoalStore
    from daylens.services.report_preview_service import native_status

    db = tmp_path / "usage.db"
    database.init_db(str(db)).close()
    store = GoalStore(tmp_path / "intelligence")
    goal = {
        "id": "out",
        "title": "完成笔记",
        "type": "outcome",
        "target_kind": None,
        "target_id": None,
        "target_minutes": None,
        "confirmed": False,
        "confirmed_at": None,
    }
    store.save_day("2026-10-20", [goal], expected_revision=0)
    path = Path(
        exporter.export_markdown(str(db), "2026-10-20", str(tmp_path / "reports"))
    )
    before = path.read_bytes()
    content = before.decode("utf-8")
    assert "一致" in native_status(str(db), content)
    store.confirm_outcome("2026-10-20", "out", True, expected_revision=1)
    assert "已变化" in native_status(str(db), content)
    assert path.read_bytes() == before


@pytest.mark.parametrize(
    "change", ["normalized_title='项目乙'", "duration_seconds=999"]
)
def test_ai_status_checks_actual_title_and_fact_eligibility(tmp_path, change):
    import sqlite3
    from datetime import date
    from daylens import database
    from daylens.services.intelligence_report_service import daily_facts
    from daylens.services.intelligence_state import load_settings
    from daylens.services.intelligence_privacy import privacy_revision
    from daylens.services.intelligence_reviews import REVIEW_PROMPT
    from daylens.services.report_evidence_service import evidence_fingerprint
    from daylens.services.report_preview_service import summary_status
    from daylens.services.report_sections import attach_summary

    db = tmp_path / "usage.db"
    conn = database.init_db(str(db))
    conn.execute("""INSERT INTO activity_sessions(session_id,start_time,end_time,date,process_name,
        window_title,normalized_title,category_key,duration_seconds,effective_seconds,
        engaged_seconds,passive_seconds,idle_seconds,metric_version,classification_version)
        VALUES ('one','2026-10-20 09:00:00','2026-10-20 09:01:00','2026-10-20','code.exe',
        '项目甲','项目甲','coding',60,60,60,0,0,'attention-v1','rules-test')""")
    conn.commit()
    conn.close()
    settings = load_settings(tmp_path / "intelligence")
    facts = [
        {k: v for k, v in fact.items() if k != "session_refs"}
        for fact in daily_facts(str(db), date(2026, 10, 20), settings)
    ]
    report = tmp_path / "one.md"
    report.write_text("# 报告", encoding="utf-8")
    attach_summary(
        report,
        "针对项目甲的汇总",
        {
            "kind": "daily",
            "period": "2026-10-20",
            "evidence_fingerprint": evidence_fingerprint(
                str(db), "daily", ["2026-10-20"]
            ),
            "facts": facts,
            "facts_version": "review-facts-v1",
            "privacy_revision": privacy_revision(settings),
            "prompt_hash": hashlib.sha256(REVIEW_PROMPT.encode()).hexdigest(),
        },
    )
    content = report.read_text(encoding="utf-8")
    assert summary_status(str(db), content) == "AI 汇总证据一致"
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE activity_sessions SET " + change)
    assert "旧数据" in summary_status(str(db), content)
