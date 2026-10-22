import json

import pytest

from daylens.services.task_decision_service import TaskDecisionStore, RevisionConflict


def test_confirm_rename_split_merge_move_and_undo_are_persistent(tmp_path):
    store = TaskDecisionStore(tmp_path)
    first = store.apply("confirm", ["s1", "s2"], "task-a", "Camera 学习", expected_revision=0)
    assert first["revision"] == 1
    assert TaskDecisionStore(tmp_path).load()["assignments"] == {"s1": "task-a", "s2": "task-a"}
    store.apply("rename", [], "task-a", "相机驱动", expected_revision=1)
    store.apply("split", ["s2"], "task-b", "文档", expected_revision=2)
    assert store.load()["assignments"]["s2"] == "task-b"
    store.apply("merge", ["s2"], "task-a", expected_revision=3)
    assert store.load()["assignments"]["s2"] == "task-a"
    store.undo(expected_revision=4)
    assert store.load()["assignments"]["s2"] == "task-b"
    assert store.load()["names"]["task-a"] == "相机驱动"


def test_stale_background_revision_cannot_overwrite_manual_confirmation(tmp_path):
    store = TaskDecisionStore(tmp_path)
    store.apply("confirm", ["s1"], "task-a", "已确认", expected_revision=0)
    with pytest.raises(RevisionConflict):
        store.apply("rename", [], "task-a", "迟到建议", expected_revision=0)
    assert store.load()["names"]["task-a"] == "已确认"


def test_corrupt_state_is_preserved_and_blocks_writes(tmp_path):
    path = tmp_path / "task_decisions.json"
    path.write_text("{broken", encoding="utf-8")
    with pytest.raises(RuntimeError):
        TaskDecisionStore(tmp_path).apply("confirm", ["s1"], "x", "测试", expected_revision=0)
    assert path.read_text(encoding="utf-8") == "{broken"


def test_corrupt_nested_decisions_are_preserved_and_block_writes(tmp_path):
    path = tmp_path / "task_decisions.json"
    state = {"version": 1, "revision": 1, "assignments": {"s1": ["bad"]},
             "names": {}, "ignored_ids": [], "history": []}
    path.write_text(json.dumps(state), encoding="utf-8")
    with pytest.raises(RuntimeError, match="格式无效"):
        TaskDecisionStore(tmp_path).load()
    assert json.loads(path.read_text(encoding="utf-8")) == state


def test_pending_commit_is_recovered_without_losing_manual_decision(tmp_path):
    store = TaskDecisionStore(tmp_path)
    pending = {"version": 1, "revision": 1, "assignments": {"s1": "task-a"},
               "names": {"task-a": "确认任务"}, "ignored_ids": [], "history": []}
    store.pending.write_text(json.dumps(pending), encoding="utf-8")
    assert store.load()["assignments"] == {"s1": "task-a"}
    assert not store.pending.exists()
