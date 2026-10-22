"""Durable task-only decisions; original sessions and classifications stay untouched."""

from __future__ import annotations

import json
import os
import threading
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from .intelligence_state import atomic_json


class RevisionConflict(RuntimeError):
    pass


_PROCESS_LOCK = threading.RLock()
_FILE_NAME = "task_decisions.json"
_PENDING_NAME = "task_decisions.pending.json"


def _blank() -> dict:
    return {"version": 1, "revision": 0, "assignments": {}, "names": {},
            "ignored_ids": [], "history": []}


def _valid_identity(value: object) -> bool:
    return type(value) is str and 1 <= len(value) <= 100


def _valid_decisions(value: dict) -> bool:
    return (
        isinstance(value.get("assignments"), dict)
        and all(_valid_identity(key) and _valid_identity(task)
                for key, task in value["assignments"].items())
        and isinstance(value.get("names"), dict)
        and all(_valid_identity(key) and type(name) is str
                and 1 <= len(name) <= 80 and not any(ord(char) < 32 for char in name)
                for key, name in value["names"].items())
        and isinstance(value.get("ignored_ids"), list)
        and all(_valid_identity(identity) for identity in value["ignored_ids"])
    )


def _read(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeError) as exc:
        raise RuntimeError("任务决策文件损坏；已停止写入并保留原文件") from exc
    if (not isinstance(value, dict) or value.get("version") != 1
            or type(value.get("revision")) is not int or value["revision"] < 0
            or not _valid_decisions(value)
            or not isinstance(value.get("history"), list)
            or len(value["history"]) > 30
            or any(not isinstance(previous, dict) or not _valid_decisions(previous)
                   for previous in value["history"])):
        raise RuntimeError("任务决策格式无效；已停止写入并保留原文件")
    return value


class TaskDecisionStore:
    def __init__(self, directory: str | Path):
        self.directory = Path(directory)
        self.path = self.directory / _FILE_NAME
        self.pending = self.directory / _PENDING_NAME

    @contextmanager
    def _locked(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        with _PROCESS_LOCK, (self.directory / "task-decisions.lock").open("a+b") as handle:
            handle.seek(0, os.SEEK_END)
            if handle.tell() == 0:
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
                        raise RuntimeError("任务决策正在保存，请稍后重试") from None
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
                raise RuntimeError("任务决策恢复版本冲突；已保留文件")
            self.pending.unlink()
        return current

    def load(self) -> dict:
        if not self.path.exists() and not self.pending.exists():
            return _blank()
        with self._locked():
            return deepcopy(self._load_locked())

    def _commit(self, state: dict) -> dict:
        atomic_json(self.pending, state)
        atomic_json(self.path, state)
        self.pending.unlink()
        return deepcopy(state)

    def apply(self, action: str, session_ids: list[str], task_id: str,
              name: str = "", *, expected_revision: int) -> dict:
        if action not in {"confirm", "rename", "split", "merge", "move", "ignore"}:
            raise ValueError("Unsupported task action")
        if (not isinstance(task_id, str) or not 1 <= len(task_id) <= 100
                or any(type(item) is not str or not 1 <= len(item) <= 100 for item in session_ids)
                or len(set(session_ids)) != len(session_ids)
                or type(expected_revision) is not int):
            raise ValueError("Invalid task identity or revision")
        if (name and (not isinstance(name, str) or len(name) > 80
                      or any(ord(char) < 32 for char in name))):
            raise ValueError("Invalid task name")
        if action in {"confirm", "split", "merge", "move"} and not session_ids:
            raise ValueError("Select at least one session")
        with self._locked():
            state = self._load_locked()
            if state["revision"] != expected_revision:
                raise RevisionConflict("任务决策已变化，请刷新后重试")
            previous = {key: deepcopy(state[key]) for key in ("assignments", "names", "ignored_ids")}
            if action in {"confirm", "split", "merge", "move"}:
                for identity in session_ids:
                    state["assignments"][identity] = task_id
            elif action == "ignore":
                state["ignored_ids"] = sorted(set(state["ignored_ids"]) | {task_id})
            if name:
                state["names"][task_id] = name.strip()
            state["history"] = (state["history"] + [previous])[-30:]
            state["revision"] += 1
            return self._commit(state)

    def undo(self, *, expected_revision: int) -> dict:
        with self._locked():
            state = self._load_locked()
            if state["revision"] != expected_revision:
                raise RevisionConflict("任务决策已变化，请刷新后重试")
            if not state["history"]:
                raise ValueError("没有可撤销的任务操作")
            previous = state["history"].pop()
            for key in ("assignments", "names", "ignored_ids"):
                state[key] = deepcopy(previous[key])
            state["revision"] += 1
            return self._commit(state)
