"""Stable read model for optional task cards and evidence details."""

from __future__ import annotations

import hashlib
import re
from datetime import date

from .. import database
from .intelligence_state import load_settings
from .task_decision_service import TaskDecisionStore
from .task_grouping_service import build_task_analysis


_GENERIC_TITLES = {
    "", "chatgpt", "daylens", "chrome", "google chrome", "edge",
    "microsoft edge", "firefox", "new tab", "新标签页", "首页",
}
_APP_DEFAULT_NAMES = {
    "chatgpt": "ChatGPT 对话",
    "chrome": "浏览器工作",
    "360chromex": "浏览器工作",
    "msedge": "浏览器工作",
    "firefox": "浏览器工作",
    "code": "编程工作",
    "python": "编程工作",
    "obsidian": "笔记整理",
    "wps": "文档工作",
    "winword": "文档工作",
}

_REVIEW_LABELS = {
    "confirmed": "已确认",
    "auto_identified": "自动识别",
    "local_candidate": "本地候选",
    "insufficient_evidence": "线索不足",
    "needs_confirmation": "待确认",
}


def task_review_label(task: dict) -> str:
    """UI label; derived recognition never implies a persisted manual decision."""
    status = task.get("review_status")
    if status is None:
        status = "confirmed" if task.get("status") == "confirmed" else "local_candidate"
    return _REVIEW_LABELS.get(str(status), "线索不足")


def _app_stem(process_name: object) -> str:
    value = str(process_name or "").strip()
    return re.sub(r"(?i)\.exe$", "", value).strip()


def _clean_title(title: object) -> str:
    value = re.sub(r"\s+", " ", str(title or "")).strip()
    value = re.sub(
        r"(?i)\s*[-–—|]\s*(?:Google Chrome|Microsoft Edge|Mozilla Firefox)$",
        "", value,
    ).strip()
    return value[:50]


def _informative_title(row: dict) -> str:
    title = _clean_title(row.get("normalized_title") or row.get("window_title"))
    stem = _app_stem(row.get("process_name"))
    if (not title or title.casefold() in _GENERIC_TITLES
            or title.casefold() == stem.casefold()
            or re.search(r"(?i)(?:https?://|www\.|[a-z0-9.-]+\.[a-z]{2,}/|[?&][\w-]+=)", title)):
        return ""
    return title


def _local_default_name(task: dict, rows_by_id: dict[str, dict]) -> tuple[str, bool]:
    ranked = []
    app_seconds: dict[str, int] = {}
    for position, identity in enumerate(task.get("source_session_ids") or []):
        row = rows_by_id.get(str(identity), {})
        seconds = max(0, int(row.get("engaged_seconds") or 0))
        title = _informative_title(row)
        if title:
            ranked.append((seconds, -position, title))
        stem = _app_stem(row.get("process_name"))
        if stem:
            app_seconds[stem] = app_seconds.get(stem, 0) + seconds
    if ranked:
        return max(ranked)[2], True
    if app_seconds:
        app = max(app_seconds, key=lambda item: (app_seconds[item], item.casefold()))
        return _APP_DEFAULT_NAMES.get(app.casefold(), f"{app} 工作"), False
    return "未命名工作", False


def _scattered_id(day: str, session_ids: list[str]) -> str:
    value = "|".join((day, *sorted(session_ids)))
    return "scattered-" + hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _decorate_and_combine(tasks: list[dict], rows: list[dict], decision: dict,
                           day: str) -> tuple[list[dict], dict[str, str]]:
    rows_by_id = {str(row.get("session_id") or ""): row for row in rows}
    decorated, scattered = [], []
    for item in tasks:
        value = dict(item)
        manual_name = decision["names"].get(item["id"])
        default_name, informative = _local_default_name(item, rows_by_id)
        value["name"] = manual_name or default_name
        value["name_source"] = "manual" if manual_name else "local_default"
        value["source"] = "人工确认" if item["status"] == "confirmed" else "本地候选"
        value["has_informative_title"] = informative
        if (item["status"] != "confirmed"
                and int(item.get("engaged_seconds") or 0) < 60
                and not informative):
            scattered.append(value)
        else:
            decorated.append(value)
    remap = {}
    if scattered:
        session_ids = [identity for item in scattered
                       for identity in item.get("source_session_ids") or []]
        task_id = _scattered_id(day, session_ids)
        candidate_ids = [item["id"] for item in scattered]
        remap = {identity: task_id for identity in candidate_ids}
        decorated.append({
            "id": task_id,
            "day": day,
            "source_session_ids": session_ids,
            "source_candidate_ids": candidate_ids,
            "start_time": min(item["start_time"] for item in scattered),
            "end_time": max(item["end_time"] for item in scattered),
            "engaged_seconds": sum(int(item.get("engaged_seconds") or 0)
                                   for item in scattered),
            "status": "needs_confirmation",
            "algorithm_version": scattered[0].get("algorithm_version"),
            "name": "零散工作活动",
            "name_source": "local_default",
            "source": "本地候选",
            "has_informative_title": False,
        })
    same_topic: dict[tuple[str, str, str, str], list[dict]] = {}
    for task in decorated:
        if task["status"] == "confirmed" or not task.get("has_informative_title"):
            continue
        signatures = set()
        for identity in task["source_session_ids"]:
            row = rows_by_id.get(identity, {})
            signatures.add((str(row.get("process_name") or "").casefold(),
                            _informative_title(row).casefold(),
                            str(row.get("category_key") or ""),
                            str(row.get("classification_version") or "")))
        if len(signatures) == 1:
            signature = next(iter(signatures))
            if all(signature):
                same_topic.setdefault(signature, []).append(task)
    consumed = set()
    for signature, members in same_topic.items():
        if len(members) < 2:
            continue
        candidate_ids = [member["id"] for member in members]
        session_ids = sorted((identity for member in members
                              for identity in member["source_session_ids"]),
                             key=lambda identity: str(rows_by_id[identity].get("start_time") or ""))
        group_id = "topic-" + hashlib.sha256(
            "|".join((day, *signature)).encode("utf-8")
        ).hexdigest()[:24]
        grouped = dict(members[0])
        grouped.update(id=group_id, source_session_ids=session_ids,
                       source_candidate_ids=candidate_ids,
                       start_time=min(member["start_time"] for member in members),
                       end_time=max(member["end_time"] for member in members),
                       engaged_seconds=sum(member["engaged_seconds"] for member in members))
        consumed.update(candidate_ids)
        remap.update({identity: group_id for identity in candidate_ids})
        decorated.append(grouped)
    decorated = [task for task in decorated if task["id"] not in consumed]
    for task in decorated:
        if task["status"] == "confirmed":
            review_status = "confirmed"
        elif task["id"].startswith("topic-"):
            review_status = "auto_identified"
        elif not task.get("has_informative_title"):
            review_status = "insufficient_evidence"
        else:
            signatures = {
                (str(rows_by_id.get(identity, {}).get("process_name") or "").casefold(),
                 _informative_title(rows_by_id.get(identity, {})).casefold(),
                 str(rows_by_id.get(identity, {}).get("category_key") or ""))
                for identity in task["source_session_ids"]
            }
            review_status = "local_candidate" if len(signatures) == 1 else "needs_confirmation"
        task["review_status"] = review_status
        if review_status == "auto_identified":
            task["source"] = "本地自动识别"
    decorated.sort(key=lambda item: (-int(item.get("engaged_seconds") or 0), item["id"]))
    return decorated, remap


def load_task_day(db_path: str, directory, day: str, *, session_loader=None) -> dict:
    settings = load_settings(directory)
    if not settings["task_analysis_enabled"]:
        return {"day": day, "status": "disabled", "tasks": [], "transitions": [],
                "revision": 0, "evidence": {}}
    date.fromisoformat(day)
    session_loader = session_loader or database.query_sessions_for_dates
    try:
        decision = TaskDecisionStore(directory).load()
        rows = session_loader(db_path, [day])
        analysis = build_task_analysis(rows, day, assignments=decision["assignments"])
    except Exception:
        # Optional analysis must never prevent recording, reports, or the dashboard.
        return {"day": day, "status": "unavailable", "tasks": [], "transitions": [],
                "revision": 0, "evidence": {}}
    ignored = set(decision["ignored_ids"])
    raw_tasks = [item for item in analysis["tasks"] if item["id"] not in ignored]
    tasks, remap = _decorate_and_combine(raw_tasks, rows, decision, day)
    tasks = [item for item in tasks if item["id"] not in ignored]
    visible_ids = {task["id"] for task in tasks}
    transitions = []
    for raw_event in analysis["transitions"]:
        event = dict(raw_event)
        event["source_task_id"] = remap.get(event["source_task_id"], event["source_task_id"])
        event["target_task_id"] = remap.get(event["target_task_id"], event["target_task_id"])
        if event["source_task_id"] in visible_ids:
            transitions.append(event)
    evidence = {}
    allowed = {identity for task in tasks for identity in task["source_session_ids"]}
    allowed.update(identity for event in transitions
                   for identity in event.get("interruption_session_ids", []))
    for row in rows:
        identity = str(row.get("session_id") or "")
        if identity in allowed:
            evidence[identity] = {
                "session_id": identity,
                "app": str(row.get("process_name") or "")[:80],
                "title": str(row.get("normalized_title") or "")[:180],
                "start_time": row.get("start_time"), "end_time": row.get("end_time"),
                "category": row.get("category_key"),
                "engaged_seconds": row.get("engaged_seconds"),
            }
    return {
        "day": day, "status": analysis["status"], "tasks": tasks,
        "transitions": transitions,
        "untrusted_session_ids": analysis["untrusted_session_ids"],
        "revision": decision["revision"], "evidence": evidence,
        "cloud_enabled": bool(settings["enabled"] and settings["task_cloud_enabled"]),
    }
