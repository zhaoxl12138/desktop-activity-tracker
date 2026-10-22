"""User-authored goals stay separate from source sessions and AI output."""

import importlib
import importlib.util
import json

import pytest


def _service():
    assert importlib.util.find_spec("daylens.services.daily_goal_service"), "daily goal service is missing"
    return importlib.import_module("daylens.services.daily_goal_service")


def _time_goal(identity="g1"):
    return {"id": identity, "type": "time_commitment", "title": "相机驱动学习",
            "target_kind": "category", "target_id": "coding", "target_minutes": 90,
            "confirmed": False, "confirmed_at": None}


def _outcome_goal(identity="g2"):
    return {"id": identity, "type": "outcome", "title": "完成课程笔记",
            "target_kind": None, "target_id": None, "target_minutes": None,
            "confirmed": False, "confirmed_at": None}


def test_save_load_revision_and_three_goal_limit(tmp_path):
    service = _service()
    store = service.GoalStore(tmp_path)
    day = "2026-10-22"
    saved = store.save_day(day, [_time_goal(), _outcome_goal()], expected_revision=0)
    assert saved["revision"] == 1
    assert store.load()["days"][day][1]["confirmed"] is False
    with pytest.raises(service.GoalRevisionConflict):
        store.save_day(day, [], expected_revision=0)
    with pytest.raises(ValueError):
        store.save_day(day, [_time_goal("a"), _time_goal("b"),
                             _time_goal("c"), _time_goal("d")], expected_revision=1)
    assert len(store.load()["days"][day]) == 2


def test_manual_outcome_confirmation_and_revocation(tmp_path):
    service = _service()
    store = service.GoalStore(tmp_path)
    day = "2026-10-22"
    store.save_day(day, [_outcome_goal()], expected_revision=0)
    checked = store.confirm_outcome(day, "g2", True, expected_revision=1)
    assert checked["days"][day][0]["confirmed"] is True
    assert checked["days"][day][0]["confirmed_at"]
    unchecked = store.confirm_outcome(day, "g2", False, expected_revision=2)
    assert unchecked["days"][day][0]["confirmed"] is False
    assert unchecked["days"][day][0]["confirmed_at"] is None


def test_editing_confirmed_outcome_clears_prior_confirmation(tmp_path):
    service = _service()
    store = service.GoalStore(tmp_path)
    day = "2026-10-22"
    store.save_day(day, [_outcome_goal()], expected_revision=0)
    checked = store.confirm_outcome(day, "g2", True, expected_revision=1)
    renamed = {**checked["days"][day][0], "title": "完成另一份报告"}
    saved = store.save_day(day, [renamed], expected_revision=2)
    assert saved["days"][day][0]["confirmed"] is False
    assert saved["days"][day][0]["confirmed_at"] is None


def test_invalid_goal_and_corrupt_state_do_not_overwrite_user_data(tmp_path):
    service = _service()
    store = service.GoalStore(tmp_path)
    with pytest.raises(ValueError):
        store.save_day("2026-10-22", [{**_time_goal(), "target_minutes": 0}],
                       expected_revision=0)
    with pytest.raises(ValueError):
        store.save_day("2026-10-22", [{**_time_goal(), "target_id": "gaming"}],
                       expected_revision=0)
    path = tmp_path / "daily_goals_v1.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError):
        store.save_day("2026-10-22", [_time_goal()], expected_revision=0)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_pending_commit_is_recovered_atomically(tmp_path):
    service = _service()
    store = service.GoalStore(tmp_path)
    pending = {"version": 1, "revision": 1,
               "days": {"2026-10-22": [_outcome_goal()]}}
    store.pending.write_text(json.dumps(pending), encoding="utf-8")
    assert store.load()["days"]["2026-10-22"][0]["id"] == "g2"
    assert not store.pending.exists()


def _session(identity, start, category="coding", engaged=60, *, version="attention-v1"):
    return {"session_id": identity, "date": "2026-10-22",
            "start_time": f"2026-10-22 09:{start}:00",
            "end_time": f"2026-10-22 09:{int(start) + 1:02d}:00",
            "category_key": category, "process_name": "code.exe",
            "normalized_title": "Camera driver", "duration_seconds": 60,
            "effective_seconds": engaged, "engaged_seconds": engaged,
            "passive_seconds": 0, "idle_seconds": 60 - engaged,
            "metric_version": version, "classification_version": "v1"}


def test_category_goal_uses_only_unique_trusted_engaged_seconds():
    service = _service()
    goals = [_time_goal()]
    first = _session("s1", "00")
    second = _session("s2", "01")
    bad = _session("bad", "02")
    bad["effective_seconds"] = 600
    legacy = _session("old", "03", version="legacy")
    result = service.evaluate_day("2026-10-22", goals,
                                  [first, first.copy(), second, bad, legacy], {})
    assert result["goals"][0]["actual_seconds"] is None
    assert result["goals"][0]["difference_seconds"] is None
    assert result["goals"][0]["evidence_status"] == "untrusted"


def test_major_work_goal_sums_apps_and_preserves_legacy_goal_meaning():
    rows = [_session("a", "00", category="coding"),
            _session("b", "01", category="ai_tools"),
            _session("c", "02", category="reading"),
            _session("d", "03", category="social")]
    major = {**_time_goal(), "target_id": "work", "title": "工作学习"}
    result = _service().evaluate_day("2026-10-22", [major, _time_goal("old")], rows, {})
    assert result["goals"][0]["actual_seconds"] == 180
    assert result["goals"][1]["actual_seconds"] == 60


def test_major_goal_categories_match_dashboard_groups():
    service = _service()
    for category, target in [("video", "entertainment"), ("gaming", "entertainment"),
                             ("finance", "finance"), ("social", "social"),
                             ("browser_general", "browser"), ("unknown", "other")]:
        assert service.goal_category_matches(target, category)
        assert sum(service.goal_category_matches(key, category)
                   for key in service.GOAL_CATEGORIES) == 1


@pytest.mark.parametrize("rows", [
    [_session("same", "00", category="coding"),
     _session("same", "00", category="office"),
     _session("other", "01", category="office")],
    [_session("same", "00", category="office"),
     _session("same", "00", category="coding"),
     _session("other", "01", category="office")],
    [_session("", "00", category="coding"),
     _session("other", "01", category="office")],
])
def test_ambiguous_relevant_rows_never_report_zero_as_complete_evidence(rows):
    result = _service().evaluate_day("2026-10-22", [_time_goal()], rows, {})
    goal = result["goals"][0]
    assert goal["actual_seconds"] is None
    assert goal["difference_seconds"] is None
    assert goal["evidence_status"] == "untrusted"


def test_confirmed_task_goal_never_counts_nearby_unassigned_sessions():
    service = _service()
    goal = {**_time_goal(), "target_kind": "task", "target_id": "task-a"}
    rows = [_session("s1", "00"), _session("s2", "01")]
    result = service.evaluate_day("2026-10-22", [goal], rows, {"s1": "task-a"})
    assert result["goals"][0]["actual_seconds"] == 60
    missing = service.evaluate_day("2026-10-22", [goal], rows, {})
    assert missing["goals"][0]["actual_seconds"] is None
    assert missing["goals"][0]["evidence_status"] == "unconfirmed_task"


def test_zero_activity_differs_from_missing_data_and_outcome_is_never_inferred():
    service = _service()
    goals = [_time_goal(), _outcome_goal()]
    missing = service.evaluate_day("2026-10-22", goals, [], {})
    assert missing["goals"][0]["actual_seconds"] is None
    assert missing["goals"][0]["evidence_status"] == "insufficient_data"
    with_data = service.evaluate_day("2026-10-22", goals,
                                     [_session("s1", "00", category="office")], {})
    assert with_data["goals"][0]["actual_seconds"] == 0
    assert with_data["goals"][1]["confirmed"] is False


def test_load_goal_day_uses_no_query_when_unconfigured_and_one_query_when_needed(tmp_path):
    service = _service()
    calls = []

    def loader(_db_path, dates):
        calls.append(dates)
        return [_session("s1", "00")]

    empty = service.load_goal_day("unused.db", tmp_path, "2026-10-22",
                                  session_loader=loader)
    assert empty["goals"] == [] and calls == []
    service.GoalStore(tmp_path).save_day("2026-10-22", [_time_goal()],
                                         expected_revision=0)
    loaded = service.load_goal_day("unused.db", tmp_path, "2026-10-22",
                                   session_loader=loader)
    assert calls == [["2026-10-22"]]
    assert loaded["goals"][0]["actual_seconds"] == 60
    assert loaded["revision"] == 1


def test_corrupt_goal_file_degrades_view_without_database_query(tmp_path):
    service = _service()
    (tmp_path / "daily_goals_v1.json").write_text("{broken", encoding="utf-8")

    def loader(*_args):
        raise AssertionError("corrupt goal state must not touch database")

    result = service.load_goal_day("unused.db", tmp_path, "2026-10-22",
                                   session_loader=loader)
    assert result["status"] == "unavailable"
    assert result["goals"] == []
