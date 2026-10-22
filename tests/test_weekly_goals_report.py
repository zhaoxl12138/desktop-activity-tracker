from datetime import date
from pathlib import Path
import sqlite3

from daylens import database, exporter
from daylens.services.daily_goal_service import GoalStore


def _time_goal():
    return {"id": "g1", "type": "time_commitment", "title": "驱动学习",
            "target_kind": "category", "target_id": "coding", "target_minutes": 90,
            "confirmed": False, "confirmed_at": None}


def _outcome_goal():
    return {"id": "g2", "type": "outcome", "title": "完成笔记",
            "target_kind": None, "target_id": None, "target_minutes": None,
            "confirmed": True, "confirmed_at": "2026-10-22T22:00:00"}


def test_weekly_review_preserves_plan_input_and_user_confirmation_separately():
    from daylens.services.daily_goal_service import build_weekly_review

    dates = [date.fromisocalendar(2026, 43, weekday).isoformat()
             for weekday in range(1, 8)]
    state = {"version": 1, "revision": 1,
             "days": {"2026-10-22": [_time_goal(), _outcome_goal()]}}
    review = build_weekly_review(dates, state, [], {})
    assert review["goal_count"] == 2
    assert review["rows"][0]["planned_seconds"] == 5400
    assert review["rows"][0]["actual_seconds"] is None
    assert review["rows"][1]["outcome_evidence"] == "用户确认"
    assert review["rows"][1]["actual_seconds"] is None


def test_generated_weekly_report_adds_goal_section_even_without_sessions(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    store = GoalStore(tmp_path / "intelligence")
    store.save_day("2026-10-22", [_time_goal(), _outcome_goal()],
                   expected_revision=0)
    store.confirm_outcome("2026-10-22", "g2", True, expected_revision=1)
    report = exporter.export_weekly_report(str(db_path), 2026, 43,
                                           str(tmp_path / "reports"))
    content = Path(report).read_text(encoding="utf-8")
    assert "计划 / 投入 / 已确认成果" in content
    assert "驱动学习" in content
    assert "证据不足" in content
    assert "完成笔记" in content and "用户确认" in content


def test_optional_weekly_goals_degrade_on_query_failure(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    GoalStore(tmp_path / "intelligence").save_day(
        "2026-10-22", [_time_goal()], expected_revision=0)

    def fail(*_args):
        raise sqlite3.OperationalError("database locked")

    monkeypatch.setattr(database, "query_sessions_for_dates", fail)
    dates = [date.fromisocalendar(2026, 43, weekday).isoformat()
             for weekday in range(1, 8)]
    assert "目标数据暂不可读" in "\n".join(exporter._weekly_goal_lines(str(db_path), dates))


def test_weekly_goal_table_shows_difference(tmp_path, monkeypatch):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    GoalStore(tmp_path / "intelligence").save_day(
        "2026-10-22", [_time_goal()], expected_revision=0)
    row = {"session_id": "s1", "date": "2026-10-22",
           "start_time": "2026-10-22 09:00:00", "end_time": "2026-10-22 09:01:00",
           "category_key": "coding", "process_name": "code.exe",
           "normalized_title": "Camera", "duration_seconds": 60,
           "effective_seconds": 60, "engaged_seconds": 60,
           "passive_seconds": 0, "idle_seconds": 0,
           "metric_version": "attention-v1", "classification_version": "v1"}
    monkeypatch.setattr(database, "query_sessions_for_dates", lambda *_args: [row])
    dates = [date.fromisocalendar(2026, 43, weekday).isoformat()
             for weekday in range(1, 8)]
    lines = exporter._weekly_goal_lines(str(db_path), dates)
    assert "偏差" in "\n".join(lines)
    assert "少 1时29分" in "\n".join(lines)
