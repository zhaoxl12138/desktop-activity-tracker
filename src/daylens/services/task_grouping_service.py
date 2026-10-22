"""Read-only, evidence-first task candidates and task-level transitions.

This module never changes classification or accounting. Its totals are a
partition of trusted source-session engaged seconds, not wall-clock time.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, datetime

from ..repositories.stats_repository import session_row_is_anomalous
from .dashboard_service import WORK_KEYS


ALGORITHM_VERSION = "task-chain-v1"
ADJACENT_SECONDS = 3 * 60
RETURN_SECONDS = 5 * 60
NON_WORK_KEYS = frozenset(("video", "gaming"))
_GENERIC = frozenset((
    "chatgpt", "chrome", "code", "document", "documentation", "window",
    "untitled", "browser", "editor", "file", "project", "页面", "首页", "文档",
))


def _identity(*parts: object) -> str:
    value = "|".join(str(part) for part in parts)
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:20]


def _topic_words(title: str) -> frozenset[str]:
    words = re.findall(r"[a-z]{4,}|[\u4e00-\u9fff]{2,}", title.casefold())
    tokens = set()
    for word in words:
        if word in _GENERIC:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", word) and len(word) >= 4:
            tokens.update(word[index:index + 4] for index in range(len(word) - 3))
        else:
            tokens.add(word)
    return frozenset(tokens - {"学习中心", "工作学习", "浏览器页"})


def _trusted(row: dict, day: str) -> tuple[datetime, datetime, int] | None:
    if row.get("metric_version") != "attention-v1" or session_row_is_anomalous(row):
        return None
    try:
        start = datetime.fromisoformat(str(row["start_time"]))
        end = datetime.fromisoformat(str(row["end_time"]))
        engaged = row["engaged_seconds"]
        effective = row["effective_seconds"]
    except (KeyError, TypeError, ValueError):
        return None
    if (start.date().isoformat() != day or end.date().isoformat() != day
            or end <= start or type(engaged) is not int
            or type(effective) is not int or not 0 <= engaged <= effective
            or engaged > (end - start).total_seconds()):
        return None
    return start, end, engaged


def _same_topic(previous: dict, current: dict) -> bool:
    if (str(previous.get("classification_version") or "")
            != str(current.get("classification_version") or "")):
        return False
    left = str(previous.get("normalized_title") or previous.get("window_title") or "").strip()
    right = str(current.get("normalized_title") or current.get("window_title") or "").strip()
    if not left or not right:
        return False
    left_words, right_words = _topic_words(left), _topic_words(right)
    if (str(previous.get("process_name") or "").casefold()
            == str(current.get("process_name") or "").casefold()
            and left.casefold() == right.casefold()):
        return True
    return bool(left_words & right_words)


def build_task_analysis(
    rows: list[dict], day: str, *, assignments: dict[str, str] | None = None,
) -> dict[str, object]:
    """Build a day-local partition of trusted work sessions and observations."""
    date.fromisoformat(day)
    assignments = assignments or {}
    dedup: dict[str, dict] = {}
    conflicts: set[str] = set()
    for row in rows:
        identity = str(row.get("session_id") or "").strip()
        if not identity:
            continue
        if identity in dedup and dedup[identity] != row:
            conflicts.add(identity)
        else:
            dedup[identity] = row

    ordered = []
    untrusted = set(conflicts)
    for identity, row in dedup.items():
        if identity in conflicts:
            continue
        valid = _trusted(row, day)
        if valid is None:
            untrusted.add(identity)
            continue
        ordered.append((valid[0], valid[1], identity, row, valid[2]))
    ordered.sort(key=lambda part: (part[0], part[1], part[2]))
    barriers = []
    for row in rows:
        if str(row.get("session_id") or "").strip() not in untrusted:
            continue
        try:
            barrier_start = datetime.fromisoformat(str(row["start_time"]))
            barrier_end = datetime.fromisoformat(str(row["end_time"]))
            if (barrier_end <= barrier_start or barrier_start.date().isoformat() != day
                    or barrier_end.date().isoformat() != day):
                raise ValueError("Unlocated untrusted evidence")
            barriers.append((barrier_start, barrier_end))
        except (KeyError, TypeError, ValueError):
            barriers.append(None)

    tasks: dict[str, dict] = {}
    transitions = []
    previous_work = None
    between = []
    for start, end, identity, row, engaged in ordered:
        category = str(row.get("category_key") or "")
        if category not in WORK_KEYS or engaged <= 0:
            if previous_work is not None:
                between.append((start, end, identity, row))
            continue
        explicit = str(assignments.get(identity) or "").strip()
        task_id = explicit
        if not task_id and previous_work is not None:
            prior_start, prior_end, prior_id, prior_row, prior_task = previous_work
            elapsed = (start - prior_end).total_seconds()
            blocked = (
                any(str(item[3].get("category_key") or "") == "idle" for item in between)
                or any(barrier is None or (barrier[0] <= start and barrier[1] >= prior_end)
                       for barrier in barriers)
            )
            allowed = RETURN_SECONDS if between else ADJACENT_SECONDS
            if (not blocked and 0 <= elapsed <= allowed
                    and _same_topic(prior_row, row)
                    and not assignments.get(prior_id)):
                task_id = prior_task
        if not task_id:
            task_id = _identity(ALGORITHM_VERSION, day, identity)
        if task_id not in tasks:
            tasks[task_id] = {
                "id": task_id, "day": day, "source_session_ids": [],
                "start_time": start.isoformat(sep=" "), "end_time": end.isoformat(sep=" "),
                "engaged_seconds": 0, "status": "needs_confirmation",
                "algorithm_version": ALGORITHM_VERSION,
            }
        task = tasks[task_id]
        task["source_session_ids"].append(identity)
        task["engaged_seconds"] += engaged
        task["start_time"] = min(task["start_time"], start.isoformat(sep=" "))
        task["end_time"] = max(task["end_time"], end.isoformat(sep=" "))
        if explicit:
            task["status"] = "confirmed"

        if previous_work is not None:
            prior_start, prior_end, prior_id, prior_row, prior_task = previous_work
            elapsed = (start - prior_end).total_seconds()
            has_barrier = any(
                barrier is None or (barrier[0] <= start and barrier[1] >= prior_end)
                for barrier in barriers
            )
            if between and 0 <= elapsed <= RETURN_SECONDS:
                categories = {str(item[3].get("category_key") or "") for item in between}
                active_nonwork = any(
                    str(item[3].get("category_key") or "") in NON_WORK_KEYS
                    and (int(item[3].get("engaged_seconds") or 0) > 0
                         or int(item[3].get("passive_seconds") or 0) > 0)
                    for item in between
                )
                event_type = (
                    "non_work_interruption" if task_id == prior_task and active_nonwork
                    and categories <= NON_WORK_KEYS else "unknown"
                )
            elif not between and 0 <= elapsed <= ADJACENT_SECONDS:
                if task_id == prior_task:
                    same_surface = (
                        str(prior_row.get("process_name") or "").casefold()
                        == str(row.get("process_name") or "").casefold()
                        and str(prior_row.get("normalized_title") or prior_row.get("window_title") or "").casefold()
                        == str(row.get("normalized_title") or row.get("window_title") or "").casefold()
                    )
                    event_type = None if same_surface else "workflow_switch"
                elif assignments.get(prior_id) and assignments.get(identity):
                    event_type = "task_switch"
                else:
                    event_type = "unknown"
            else:
                event_type = "unknown"
            if (has_barrier or str(prior_row.get("classification_version") or "")
                    != str(row.get("classification_version") or "")):
                event_type = "unknown"
            if event_type is not None and 0 <= elapsed <= RETURN_SECONDS:
                transitions.append({
                    "event_id": _identity("transition-v1", prior_id, identity),
                    "source_task_id": prior_task,
                    "target_task_id": task_id,
                    "source_session_ids": [prior_id],
                    "interruption_session_ids": [item[2] for item in between],
                    "return_session_ids": [identity] if task_id == prior_task else [],
                    "event_type": event_type,
                    "target_category": (
                        str(between[0][3].get("category_key") or "") if between else category
                    ),
                    "start_time": prior_end.isoformat(sep=" "),
                    "end_time": start.isoformat(sep=" "),
                    "returned_to_source_task": (
                        "yes" if event_type == "non_work_interruption" else "unknown"
                    ),
                    "interruption_elapsed_seconds": (
                        int(elapsed) if between and elapsed >= 0 else None
                    ),
                    "return_gap_seconds": (
                        int((start - between[-1][1]).total_seconds())
                        if event_type == "non_work_interruption" else None
                    ),
                    "evidence_ids": [prior_id, *(item[2] for item in between), identity],
                    "trust_status": "ready" if event_type != "unknown" else "needs_confirmation",
                    "analysis_version": ALGORITHM_VERSION,
                })
        previous_work = (start, end, identity, row, task_id)
        between = []

    values = sorted(tasks.values(), key=lambda task: (-task["engaged_seconds"], task["id"]))
    return {
        "day": day, "status": "ready" if values else "insufficient_data",
        "tasks": values, "transitions": transitions,
        "untrusted_session_ids": sorted(untrusted),
        "algorithm_version": ALGORITHM_VERSION,
    }
