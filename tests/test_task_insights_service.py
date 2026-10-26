from daylens.services.intelligence_state import save_settings
from daylens.services.task_insights_service import load_task_day
from daylens.services.task_decision_service import TaskDecisionStore


def test_disabled_task_analysis_does_not_read_database(tmp_path):
    def forbidden(*_args):
        raise AssertionError("disabled task analysis must not read sessions")
    model = load_task_day("unused.db", tmp_path, "2026-10-21", session_loader=forbidden)
    assert model["status"] == "disabled"


def test_confirmed_task_name_decorates_local_totals_without_rewriting_source(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    TaskDecisionStore(tmp_path).apply("confirm", ["s1"], "task-a", "相机任务", expected_revision=0)
    rows = [{"session_id": "s1", "date": "2026-10-21",
             "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:01:00",
             "process_name": "code.exe", "normalized_title": "Camera work",
             "category_key": "coding", "engaged_seconds": 60, "effective_seconds": 60,
             "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 60,
             "metric_version": "attention-v1"}]
    model = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)
    assert model["tasks"][0]["name"] == "相机任务"
    assert model["tasks"][0]["engaged_seconds"] == 60
    assert model["tasks"][0]["status"] == "confirmed"
    assert rows[0]["category_key"] == "coding"


def test_task_detail_keeps_nonwork_insertion_evidence_separate_from_task_time(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [
        {"session_id": identity, "date": "2026-10-21",
         "start_time": f"2026-10-21 09:0{index}:00",
         "end_time": f"2026-10-21 09:0{index}:50",
         "process_name": "code.exe" if identity != "v" else "player.exe",
         "normalized_title": "Camera driver" if identity != "v" else "Film",
         "category_key": "coding" if identity != "v" else "video",
         "engaged_seconds": 50 if identity != "v" else 0,
         "effective_seconds": 50, "passive_seconds": 0 if identity != "v" else 50,
         "idle_seconds": 0, "duration_seconds": 50,
         "metric_version": "attention-v1"}
        for index, identity in enumerate(("s1", "v", "s2"))
    ]
    model = load_task_day("unused.db", tmp_path, "2026-10-21", session_loader=lambda *_: rows)
    assert "v" in model["evidence"]
    assert sum(task["engaged_seconds"] for task in model["tasks"]) == 100


def test_unnamed_candidate_gets_a_readable_local_default_name(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [{
        "session_id": "s1", "date": "2026-10-21",
        "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:01:00",
        "process_name": "ChatGPT.exe", "normalized_title": "ChatGPT",
        "category_key": "coding", "engaged_seconds": 60, "effective_seconds": 60,
        "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 60,
        "metric_version": "attention-v1",
    }]

    model = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)

    assert model["tasks"][0]["name"] == "ChatGPT 对话"
    assert model["tasks"][0]["name_source"] == "local_default"


def test_same_titled_work_is_one_reviewable_candidate_across_long_gaps(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    def item(identity, hour, app="chrome.exe", category="coding"):
        return {"session_id": identity, "date": "2026-10-21",
                "start_time": f"2026-10-21 {hour}:00:00",
                "end_time": f"2026-10-21 {hour}:01:00",
                "process_name": app, "normalized_title": "自考笔果题库【官网】",
                "category_key": category, "engaged_seconds": 60,
                "effective_seconds": 60, "passive_seconds": 0,
                "idle_seconds": 0, "duration_seconds": 60,
                "metric_version": "attention-v1", "classification_version": "rules-a"}
    rows = [item("s1", "09"), item("s2", "11"), item("s3", "13", "other.exe")]
    model = load_task_day("unused.db", tmp_path, "2026-10-21", session_loader=lambda *_: rows)
    assert len(model["tasks"]) == 2
    grouped = next(task for task in model["tasks"] if set(task["source_session_ids"]) == {"s1", "s2"})
    assert grouped["engaged_seconds"] == 120
    assert grouped["status"] == "needs_confirmation"
    assert len(grouped["source_candidate_ids"]) == 2
    assert grouped["review_status"] == "auto_identified"
    other = next(task for task in model["tasks"] if task["source_session_ids"] == ["s3"])
    assert other["review_status"] == "local_candidate"


def test_short_generic_candidates_are_combined_as_scattered_work(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [
        {
            "session_id": "s1", "date": "2026-10-21",
            "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:00:30",
            "process_name": "ChatGPT.exe", "normalized_title": "ChatGPT",
            "category_key": "coding", "engaged_seconds": 30, "effective_seconds": 30,
            "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 30,
            "metric_version": "attention-v1",
        },
        {
            "session_id": "s2", "date": "2026-10-21",
            "start_time": "2026-10-21 09:10:00", "end_time": "2026-10-21 09:10:20",
            "process_name": "ChatGPT.exe", "normalized_title": "ChatGPT",
            "category_key": "coding", "engaged_seconds": 20, "effective_seconds": 20,
            "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 20,
            "metric_version": "attention-v1",
        },
    ]

    model = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)

    assert len(model["tasks"]) == 1
    assert model["tasks"][0]["name"] == "零散工作活动"
    assert model["tasks"][0]["review_status"] == "insufficient_evidence"
    assert model["tasks"][0]["engaged_seconds"] == 50
    assert model["tasks"][0]["source_session_ids"] == ["s1", "s2"]


def test_informative_title_is_used_as_the_default_task_name(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [{
        "session_id": "s1", "date": "2026-10-21",
        "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:00:40",
        "process_name": "chrome.exe", "normalized_title": "AI化优化方案",
        "category_key": "coding", "engaged_seconds": 40, "effective_seconds": 40,
        "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 40,
        "metric_version": "attention-v1",
    }]

    model = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)

    assert model["tasks"][0]["name"] == "AI化优化方案"
    assert model["tasks"][0]["review_status"] == "local_candidate"


def test_ignored_scattered_work_does_not_reappear_after_refresh(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [{
        "session_id": "s1", "date": "2026-10-21",
        "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:00:30",
        "process_name": "ChatGPT.exe", "normalized_title": "ChatGPT",
        "category_key": "coding", "engaged_seconds": 30, "effective_seconds": 30,
        "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 30,
        "metric_version": "attention-v1",
    }]
    first = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)
    scattered_id = first["tasks"][0]["id"]
    TaskDecisionStore(tmp_path).apply(
        "ignore", [], scattered_id, expected_revision=first["revision"]
    )

    refreshed = load_task_day("unused.db", tmp_path, "2026-10-21",
                              session_loader=lambda *_: rows)

    assert refreshed["tasks"] == []


def test_url_like_window_title_is_not_used_as_a_task_name(tmp_path):
    save_settings(tmp_path, {"task_analysis_enabled": True})
    rows = [{
        "session_id": "s1", "date": "2026-10-21",
        "start_time": "2026-10-21 09:00:00", "end_time": "2026-10-21 09:01:00",
        "process_name": "chrome.exe",
        "normalized_title": "accounts.google.com/v3/signin/accountchooser?client=private",
        "category_key": "coding", "engaged_seconds": 60, "effective_seconds": 60,
        "passive_seconds": 0, "idle_seconds": 0, "duration_seconds": 60,
        "metric_version": "attention-v1",
    }]

    model = load_task_day("unused.db", tmp_path, "2026-10-21",
                          session_loader=lambda *_: rows)

    assert model["tasks"][0]["name"] == "浏览器工作"
    assert "client" not in model["tasks"][0]["name"]
