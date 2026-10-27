"""Versioned user goals, separate from recording, classification and AI claims."""

from __future__ import annotations

import json
import os
import re
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from pathlib import Path

from ..utils import WORK_CATEGORY_KEYS
from .intelligence_state import atomic_json
from .task_grouping_service import _trusted


class GoalRevisionConflict(RuntimeError):
    """The editor's snapshot is older than the durable goal state."""


_LOCK = threading.RLock()
_FILE = "daily_goals_v1.json"
_PENDING = "daily_goals_v1.pending.json"
_IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,100}\Z")
_WORK_CATEGORIES = WORK_CATEGORY_KEYS
GOAL_CATEGORIES = {
    "work": "工作学习", "entertainment": "娱乐休闲", "social": "社交通讯",
    "finance": "投资理财", "browser": "浏览器", "tools": "系统工具", "other": "其他",
}


def goal_category_matches(target: str, category: str) -> bool:
    if target not in GOAL_CATEGORIES:
        return category == target  # Existing detailed goals retain their meaning.
    from .dashboard_service import category_seconds
    return category_seconds({"by_category": [
        {"category_key": category, "effective_seconds": 1}
    ]}).get(target, 0) == 1


def _blank() -> dict:
    return {"version": 1, "revision": 0, "days": {}}


def _valid_day(value: object) -> bool:
    if type(value) is not str:
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_goal(goal: object) -> bool:
    if not isinstance(goal, dict) or set(goal) != {
        "id", "type", "title", "target_kind", "target_id", "target_minutes",
        "confirmed", "confirmed_at",
    }:
        return False
    if (type(goal["id"]) is not str or not _IDENTIFIER.fullmatch(goal["id"])
            or type(goal["title"]) is not str
            or not 1 <= len(goal["title"].strip()) <= 80
            or any(ord(char) < 32 for char in goal["title"])
            or type(goal["confirmed"]) is not bool):
        return False
    if goal["type"] == "time_commitment":
        return (
            goal["target_kind"] in ("task", "category")
            and type(goal["target_id"]) is str
            and bool(_IDENTIFIER.fullmatch(goal["target_id"]))
            and (goal["target_kind"] != "category"
                 or goal["target_id"] in _WORK_CATEGORIES | GOAL_CATEGORIES.keys())
            and type(goal["target_minutes"]) is int
            and 1 <= goal["target_minutes"] <= 1440
            and goal["confirmed"] is False
            and goal["confirmed_at"] is None
        )
    if goal["type"] == "outcome":
        return (
            goal["target_kind"] is None and goal["target_id"] is None
            and goal["target_minutes"] is None
            and (goal["confirmed_at"] is None if not goal["confirmed"]
                 else type(goal["confirmed_at"]) is str
                 and len(goal["confirmed_at"]) <= 32)
        )
    return False


def _valid_state(value: object) -> bool:
    if (not isinstance(value, dict) or set(value) != {"version", "revision", "days"}
            or value["version"] != 1 or type(value["revision"]) is not int
            or value["revision"] < 0 or not isinstance(value["days"], dict)):
        return False
    for day, goals in value["days"].items():
        if (not _valid_day(day) or not isinstance(goals, list)
                or len(goals) > 3 or not all(_valid_goal(goal) for goal in goals)
                or len({goal["id"] for goal in goals}) != len(goals)):
            return False
    return True


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RuntimeError("每日目标文件损坏；已保留原文件并停止写入") from exc
    if not _valid_state(value):
        raise RuntimeError("每日目标格式无效；已保留原文件并停止写入")
    return value


class GoalStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.path = self.directory / _FILE
        self.pending = self.directory / _PENDING

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with _LOCK, (self.directory / "daily-goals.lock").open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if not handle.tell():
                handle.write(b"0")
                handle.flush()
            deadline = time.monotonic() + 5
            while True:
                try:
                    handle.seek(0)
                    if os.name == "nt":
                        import msvcrt
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                    else:
                        import fcntl
                        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise RuntimeError("每日目标正在保存，请稍后重试") from None
                    time.sleep(.01)
            try:
                yield
            finally:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)

    def _load_locked(self) -> dict:
        current = _read(self.path) or _blank()
        pending = _read(self.pending)
        if pending is not None:
            if pending["revision"] == current["revision"] + 1:
                atomic_json(self.path, pending)
                current = pending
            elif pending["revision"] != current["revision"]:
                raise RuntimeError("每日目标恢复版本冲突；已保留文件")
            self.pending.unlink()
        return current

    def load(self) -> dict:
        with self._locked():
            return deepcopy(self._load_locked())

    def _commit(self, state: dict) -> dict:
        atomic_json(self.pending, state)
        atomic_json(self.path, state)
        self.pending.unlink()
        return deepcopy(state)

    def save_day(self, day: str, goals: list[dict], *, expected_revision: int) -> dict:
        if (not _valid_day(day) or not isinstance(goals, list)
                or len(goals) > 3 or not all(_valid_goal(goal) for goal in goals)
                or len({goal["id"] for goal in goals}) != len(goals)
                or type(expected_revision) is not int):
            raise ValueError("每日目标格式无效；每天最多 3 项")
        with self._locked():
            state = self._load_locked()
            if state["revision"] != expected_revision:
                raise GoalRevisionConflict("每日目标已变化，请刷新后重试")
            previous = {item["id"]: item for item in state["days"].get(day, [])}
            revised = deepcopy(goals)
            for item in revised:
                if item["type"] != "outcome":
                    continue
                old = previous.get(item["id"])
                if old and old["type"] == "outcome" and old["title"] == item["title"]:
                    item["confirmed"] = old["confirmed"]
                    item["confirmed_at"] = old["confirmed_at"]
                else:
                    item["confirmed"] = False
                    item["confirmed_at"] = None
            state["days"][day] = revised
            state["revision"] += 1
            return self._commit(state)

    def confirm_outcome(self, day: str, goal_id: str, confirmed: bool,
                        *, expected_revision: int) -> dict:
        if (not _valid_day(day) or type(goal_id) is not str
                or type(confirmed) is not bool or type(expected_revision) is not int):
            raise ValueError("成果确认参数无效")
        with self._locked():
            state = self._load_locked()
            if state["revision"] != expected_revision:
                raise GoalRevisionConflict("每日目标已变化，请刷新后重试")
            goal = next((item for item in state["days"].get(day, [])
                         if item["id"] == goal_id), None)
            if goal is None or goal["type"] != "outcome":
                raise ValueError("找不到可确认的成果目标")
            goal["confirmed"] = confirmed
            goal["confirmed_at"] = (datetime.now().isoformat(timespec="seconds")
                                    if confirmed else None)
            state["revision"] += 1
            return self._commit(state)


def evaluate_day(day: str, goals: list[dict], rows: list[dict],
                 assignments: dict[str, str]) -> dict:
    """Compare a plan with trusted engaged seconds; never infer an outcome."""
    if not _valid_day(day) or not all(_valid_goal(goal) for goal in goals):
        raise ValueError("每日目标或日期格式无效")
    dedup = {}
    conflicts = set()
    ambiguous = []
    for row in rows:
        identity = str(row.get("session_id") or "").strip()
        if not identity:
            ambiguous.append(row)
            continue
        if identity in dedup and dedup[identity] != row:
            conflicts.add(identity)
            ambiguous.append(row)
        else:
            dedup[identity] = row
    trusted, untrusted = {}, {}
    for identity, row in dedup.items():
        if identity in conflicts or _trusted(row, day) is None:
            untrusted[identity] = row
        else:
            trusted[identity] = row
    for row in ambiguous:
        untrusted[f"ambiguous-{len(untrusted)}"] = row

    evaluated = []
    for goal in goals:
        item = deepcopy(goal)
        item["actual_seconds"] = None
        item["difference_seconds"] = None
        if goal["type"] == "outcome":
            item["evidence_status"] = "user_confirmed" if goal["confirmed"] else "awaiting_user"
            evaluated.append(item)
            continue
        target = goal["target_id"]
        if goal["target_kind"] == "task":
            assigned = {identity for identity, task_id in assignments.items()
                        if task_id == target}
            relevant = lambda identity, row: identity in assigned
            if not assigned:
                item["evidence_status"] = "unconfirmed_task"
                evaluated.append(item)
                continue
        else:
            relevant = lambda identity, row: goal_category_matches(target, row.get("category_key", ""))
        uncertain = any(relevant(identity, row) for identity, row in untrusted.items())
        matching = [row for identity, row in trusted.items() if relevant(identity, row)]
        if uncertain:
            item["evidence_status"] = "untrusted"
        elif not trusted and not matching:
            item["evidence_status"] = "insufficient_data"
        elif goal["target_kind"] == "task" and not matching:
            item["evidence_status"] = "untrusted"
        else:
            actual = sum(int(row["engaged_seconds"]) for row in matching)
            item["actual_seconds"] = actual
            item["difference_seconds"] = goal["target_minutes"] * 60 - actual
            item["evidence_status"] = "ready"
        evaluated.append(item)
    return {"day": day, "goals": evaluated,
            "status": "ready" if rows else "insufficient_data",
            "trusted_session_count": len(trusted),
            "untrusted_session_count": len(untrusted)}


def load_goal_day(db_path: str, directory: str | Path, day: str,
                  *, session_loader=None) -> dict:
    """Read one day's goal view without changing the source database."""
    if not _valid_day(day):
        raise ValueError("目标日期无效")
    try:
        state = GoalStore(directory).load()
        goals = state["days"].get(day, [])
        if not goals:
            return {"day": day, "goals": [], "status": "no_goals",
                    "revision": state["revision"]}
        rows = []
        assignments = {}
        if any(goal["type"] == "time_commitment" for goal in goals):
            if session_loader is None:
                from .. import database
                session_loader = database.query_sessions_for_dates
            rows = session_loader(db_path, [day])
            if any(goal["target_kind"] == "task" for goal in goals):
                from .task_decision_service import TaskDecisionStore
                assignments = TaskDecisionStore(directory).load()["assignments"]
        result = evaluate_day(day, goals, rows, assignments)
        result["revision"] = state["revision"]
        return result
    except Exception:
        # Optional goal analysis must never stop recording or the old reports.
        return {"day": day, "goals": [], "status": "unavailable", "revision": 0}


def build_weekly_review(dates: list[str], state: dict, rows: list[dict],
                        assignments: dict[str, str]) -> dict:
    """Keep goal rows separate so overlapping targets are never summed twice."""
    if len(dates) != 7 or not all(_valid_day(day) for day in dates) or not _valid_state(state):
        raise ValueError("周目标范围或状态无效")
    by_day = {day: [] for day in dates}
    for row in rows:
        day = str(row.get("date") or "")
        if day in by_day:
            by_day[day].append(row)
    result = []
    for day in dates:
        goals = state["days"].get(day, [])
        if not goals:
            continue
        evaluated = evaluate_day(day, goals, by_day[day], assignments)
        for goal in evaluated["goals"]:
            result.append({
                "day": day, "id": goal["id"], "title": goal["title"],
                "type": goal["type"],
                "planned_seconds": (goal["target_minutes"] * 60
                                    if goal["type"] == "time_commitment" else None),
                "actual_seconds": goal["actual_seconds"],
                "difference_seconds": goal["difference_seconds"],
                "evidence_status": goal["evidence_status"],
                "outcome_evidence": (
                    "用户确认" if goal["confirmed"] else "未确认"
                ) if goal["type"] == "outcome" else None,
            })
    return {"dates": dates, "goal_count": len(result), "rows": result}
