"""Evidence-first task grouping, independent from recording and reports."""

from daylens.services.task_grouping_service import build_task_analysis
from daylens import database
from daylens.session_tracker import ActivitySession
from datetime import datetime, timedelta


def row(identity, start, end, app, title, category="coding", engaged=60):
    return {
        "session_id": identity, "date": "2026-10-21",
        "start_time": f"2026-10-21 {start}", "end_time": f"2026-10-21 {end}",
        "process_name": app, "normalized_title": title,
        "category_key": category, "engaged_seconds": engaged,
        "effective_seconds": engaged, "passive_seconds": 0,
        "idle_seconds": 0, "duration_seconds": max(60, engaged),
        "metric_version": "attention-v1",
        "classification_version": "v1",
    }


def test_cross_app_topic_evidence_groups_without_double_counting():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver code"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "Camera driver documentation"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "Camera driver documentation"),
    ]
    result = build_task_analysis(rows, "2026-10-21")
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["engaged_seconds"] == 120
    assert result["tasks"][0]["source_session_ids"] == ["s1", "s2"]
    assert result["transitions"][0]["event_type"] == "workflow_switch"


def test_nearby_unrelated_titles_are_not_forced_into_one_task():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver code"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "Recipe for dinner"),
    ]
    result = build_task_analysis(rows, "2026-10-21")
    assert len(result["tasks"]) == 2
    assert all(task["status"] == "needs_confirmation" for task in result["tasks"])


def test_entertainment_insert_can_return_but_social_stays_unknown():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver code"),
        row("v", "09:01:10", "09:02:10", "player.exe", "A film", "video", 0),
        row("s2", "09:02:20", "09:03:20", "code.exe", "Camera driver code"),
    ]
    rows[1]["passive_seconds"] = 60
    rows[1]["effective_seconds"] = 60
    result = build_task_analysis(rows, "2026-10-21")
    assert result["tasks"][0]["engaged_seconds"] == 120
    assert result["transitions"][0]["event_type"] == "non_work_interruption"
    assert result["transitions"][0]["returned_to_source_task"] == "yes"
    assert result["transitions"][0]["interruption_elapsed_seconds"] == 80
    assert result["transitions"][0]["return_gap_seconds"] == 10
    rows[1]["category_key"] = "social"
    result = build_task_analysis(rows, "2026-10-21")
    assert result["transitions"][0]["event_type"] == "unknown"


def test_legacy_gap_and_duplicate_conflict_do_not_create_trusted_time():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver code"),
        row("legacy", "09:01:10", "09:02:10", "code.exe", "Camera driver code"),
    ]
    rows[1]["metric_version"] = "legacy"
    result = build_task_analysis(rows, "2026-10-21")
    assert sum(task["engaged_seconds"] for task in result["tasks"]) == 60
    assert result["untrusted_session_ids"] == ["legacy"]


def test_malformed_metric_composition_is_not_counted_as_task_time():
    sample = row("broken", "09:00:00", "09:01:00", "code.exe", "Camera driver")
    sample["effective_seconds"] = 600
    result = build_task_analysis([sample], "2026-10-21")
    assert result["tasks"] == []
    assert result["untrusted_session_ids"] == ["broken"]


def test_untrusted_record_between_work_sessions_blocks_automatic_link():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver"),
        row("bad", "09:01:05", "09:02:05", "player.exe", "Film", "video"),
        row("s2", "09:02:10", "09:03:10", "code.exe", "Camera driver"),
    ]
    rows[1]["effective_seconds"] = 600
    result = build_task_analysis(rows, "2026-10-21")
    assert len(result["tasks"]) == 2
    assert result["untrusted_session_ids"] == ["bad"]
    assert result["transitions"][0]["event_type"] == "unknown"


def test_same_app_and_same_title_continuation_is_not_a_tool_switch():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver"),
        row("s2", "09:01:10", "09:02:10", "code.exe", "Camera driver"),
    ]
    result = build_task_analysis(rows, "2026-10-21")
    assert len(result["tasks"]) == 1
    assert not result["transitions"]


def test_manual_assignment_can_join_unrelated_sessions_without_reclassifying():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver code"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "Recipe for dinner"),
    ]
    result = build_task_analysis(rows, "2026-10-21", assignments={"s1": "my-task", "s2": "my-task"})
    assert len(result["tasks"]) == 1
    assert result["tasks"][0]["id"] == "my-task"
    assert result["tasks"][0]["engaged_seconds"] == 120


def test_distinct_confirmed_tasks_are_a_task_switch_not_an_interruption():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "Recruiting search"),
    ]
    result = build_task_analysis(rows, "2026-10-21",
                                 assignments={"s1": "task-a", "s2": "task-b"})
    assert result["transitions"][0]["event_type"] == "task_switch"
    assert result["transitions"][0]["returned_to_source_task"] == "unknown"


def test_classification_version_boundary_prevents_auto_grouping():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "Camera driver"),
        row("s2", "09:01:10", "09:02:10", "code.exe", "Camera driver"),
    ]
    rows[1]["classification_version"] = "v2"
    result = build_task_analysis(rows, "2026-10-21")
    assert len(result["tasks"]) == 2
    assert result["transitions"][0]["event_type"] == "unknown"


def test_chinese_cross_app_topic_requires_distinctive_shared_phrase():
    rows = [
        row("s1", "09:00:00", "09:01:00", "code.exe", "摄像头驱动学习"),
        row("s2", "09:01:10", "09:02:10", "chrome.exe", "摄像头驱动文档"),
    ]
    assert len(build_task_analysis(rows, "2026-10-21")["tasks"]) == 1
    rows[1]["normalized_title"] = "学习中心首页"
    assert len(build_task_analysis(rows, "2026-10-21")["tasks"]) == 2


def test_existing_single_date_query_exposes_switch_reason_without_writing(tmp_path):
    db_path = str(tmp_path / "usage.db")
    conn = database.init_db(db_path)
    start = datetime(2026, 10, 21, 9, 0)
    database.insert_session(conn, ActivitySession(
        session_id="s1", start_time=start, end_time=start + timedelta(seconds=60),
        date="2026-10-21", process_name="code.exe", exe_path="", window_title="Camera",
        normalized_title="Camera", category_key="coding", category_name="开发",
        active_rule="interactive_required", duration_seconds=60, effective_seconds=60,
        engaged_seconds=60, passive_seconds=0, idle_seconds=0,
        switch_reason="foreground_changed",
    ))
    database.close_db(conn)
    rows = database.query_sessions_for_dates(db_path, ["2026-10-21"])
    assert len(rows) == 1
    assert rows[0]["switch_reason"] == "foreground_changed"
