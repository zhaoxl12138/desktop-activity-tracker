from datetime import date, timedelta
from pathlib import Path

import pytest

from daylens.services.behavior_profile_service import dates_before, summarize, load_profiles, profile_lines
from daylens.services.behavior_experiment_service import ExperimentStore, feedback
from daylens.services.intelligence_state import save_settings, load_settings


def row(day, identity="a", minute=0, category="coding", version="v1"):
    return {"session_id": f"{day}-{identity}", "date": day,
            "start_time": f"{day} 09:{minute:02d}:00",
            "end_time": f"{day} 09:{minute+1:02d}:00",
            "duration_seconds": 60, "effective_seconds": 60, "engaged_seconds": 60,
            "passive_seconds": 0, "idle_seconds": 0,
            "category_key": category, "metric_version": "attention-v1",
            "classification_version": version, "normalized_title": "Camera driver",
            "process_name": "code.exe"}


def enable(directory):
    save_settings(directory, {**load_settings(directory), "behavior_analysis_enabled": True})


def test_profiles_disabled_never_queries(tmp_path):
    def forbidden(*args):
        raise AssertionError("must not query")
    assert load_profiles("db", tmp_path, loader=forbidden)["status"] == "disabled"


def test_profiles_one_read_windows_dedup_and_completed_dates(tmp_path):
    enable(tmp_path)
    calls = []
    end = date(2026, 10, 1)
    def loader(db, days):
        calls.append(days)
        rows = [row(day) for day in days]
        return rows + [rows[0].copy()]
    result = load_profiles("db", tmp_path, end, loader=loader)
    assert len(calls) == 1
    for n, model in result["profiles"].items():
        assert len(model["dates"]) == n
        assert model["dates"][-1] == "2026-09-30"
        assert model["ready"]
        assert model["work_seconds"] == n * 60
        assert model["trend"]["work"] == [60, 60]


@pytest.mark.parametrize("problem", ["missing", "legacy", "version", "overlap", "conflict", "no-id"])
def test_uncomparable_data_suppresses_trends(problem):
    days = dates_before(date(2026, 10, 1), 7)
    rows = [row(day) for day in days]
    if problem == "missing":
        rows.pop()
    elif problem == "legacy":
        rows[0]["metric_version"] = "legacy"
    elif problem == "version":
        rows[0]["classification_version"] = "v2"
    elif problem == "no-id":
        rows[0]["session_id"] = ""
    else:
        rows.append({**rows[0], "session_id": "different" if problem == "overlap" else rows[0]["session_id"],
                     "category_key": "office"})
    result = summarize(rows, days)
    assert not result["ready"]
    assert result["trend"] is None
    assert result["insertion_rate"] is None


def test_partial_profile_reports_verified_lower_bound_and_precise_gaps():
    days = dates_before(date(2026, 10, 1), 7)
    rows = [row(day) for day in days]
    rows[0]["classification_version"] = "older"
    rows.append({**row(days[-1], "cross", 2), "end_time": "2026-10-01 00:00:00"})
    result = summarize(rows, days)
    shown = "\n".join(profile_lines({"status": "ready", "profiles": {7: result}}))
    assert not result["ready"]
    assert result["trend"] is None
    assert result["excluded_session_count"] == 1
    assert "跨日期会话 1 条" in shown
    assert "分类版本" in shown
    assert "已核实片段：工作参与 7 分钟" in shown
    assert "不代表全天或区间总量" in shown
    assert "前半段 → 后半段" not in shown


def test_conflicting_session_identity_is_not_counted_as_verified_partial():
    day = "2026-09-30"
    first = row(day)
    second = {**first, "category_key": "office"}
    result = summarize([first, second], [day])
    assert not result["ready"]
    assert result["work_seconds"] == 0
    assert result["conflicting_session_count"] == 1


def test_interruption_evidence_and_continuity_are_distinct():
    day = "2026-10-01"
    rows = [row(day), row(day, "b", 1, "video"), row(day, "c", 2), row(day, "d", 3)]
    result = summarize(rows, [day])
    assert result["insertions"] == 1
    assert result["daily"][0]["longest"] == 120
    assert result["daily"][0]["task_longest"] == 120
    assert result["work_seconds"] == 180
    assert result["entertainment_hours"] == {9: 60}
    assert result["inserted_tasks"][0]["session_ids"] == [f"{day}-a", f"{day}-c", f"{day}-d"]


def test_experiment_requires_valid_baseline_and_explicit_acceptance(tmp_path):
    today = date(2026, 10, 1)
    days = dates_before(today, 7)
    baseline = summarize([row(day) for day in days], days)
    store = ExperimentStore(tmp_path)
    assert store.load() is None
    with pytest.raises(ValueError):
        store.accept(baseline, today)
    enable(tmp_path)
    value = store.accept(baseline, today)
    assert value["start"] == "2026-10-02"
    assert value["end"] == "2026-10-08"
    assert feedback("db", tmp_path, date(2026, 9, 30)) == "该日期尚未接受实验。"
    with pytest.raises(ValueError):
        store.accept(baseline, today)
    assert "等待" in feedback("db", tmp_path, date(2026, 10, 8))
    rows = [row(day) for day in days + dates_before(date(2026, 10, 9), 7)]
    result = feedback("db", tmp_path, date(2026, 10, 9), loader=lambda *_: rows)
    assert "0.00 → 0.00" in result
    assert "不能证明" in result
    assert "Camera driver" not in store.path.read_text(encoding="utf-8")
    rows[0]["normalized_title"] = "changed evidence"
    assert "不能评价" in feedback("db", tmp_path, date(2026, 10, 9), loader=lambda *_: rows)
    store.stop()
    assert feedback("db", tmp_path) == "实验已停止。"


def test_corrupt_experiment_preserved(tmp_path):
    store = ExperimentStore(tmp_path)
    store.path.write_text("{broken", encoding="utf-8")
    with pytest.raises(ValueError):
        store.stop()
    assert store.path.read_text() == "{broken"


def test_enabled_weekly_report_contains_profile_without_replacing_goals(tmp_path):
    from daylens import database, exporter
    db = tmp_path / "usage.db"
    database.init_db(str(db)).close()
    enable(tmp_path / "intelligence")
    path = exporter.export_weekly_report(str(db), 2026, 40, str(tmp_path / "reports"))
    text = Path(path).read_text(encoding="utf-8")
    assert "行为画像" in text and "近7个完整日" in text and "近30个完整日" in text
    assert "暂不生成画像和趋势" in text


def test_dialog_disabled_state_never_offers_experiment(tmp_path):
    import time
    from PySide6.QtWidgets import QApplication
    from daylens.gui.widgets.behavior_dialog import BehaviorDialog
    app = QApplication.instance() or QApplication([])
    dialog = BehaviorDialog("unused", tmp_path)
    deadline = time.monotonic() + 3
    while dialog.model is None and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(.01)
    assert dialog.model["status"] == "disabled"
    assert not dialog.accept_button.isEnabled()
    assert "设置中心" in dialog.text.toPlainText()
    dialog.close()
    dialog.timer.stop()


@pytest.mark.parametrize("size", [(1280, 720), (1920, 1080)])
def test_reports_behavior_entry_fits_window(tmp_path, size):
    from PySide6.QtWidgets import QApplication
    from daylens.gui.pages.reports import ReportsPage
    app = QApplication.instance() or QApplication([])
    page = ReportsPage(str(tmp_path / "usage.db"), str(tmp_path / "reports"))
    # Reserve shell sidebar space, as in the actual main window.
    page.resize(size[0] - 240, size[1] - 140)
    page.show()
    app.processEvents()
    assert page.width() <= size[0] - 240
    button = page.btn_behavior
    assert button.isVisible()
    assert button.geometry().right() < page.btn_open_dir.geometry().left()
    assert button.parentWidget().width() <= page.width()
    page.close()
