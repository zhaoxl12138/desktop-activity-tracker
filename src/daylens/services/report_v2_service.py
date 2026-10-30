"""Read-only, single-snapshot report facts. No AI or recording dependencies."""

from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime, timedelta
import hashlib
import json
from pathlib import Path
import sqlite3

from ..app_paths import AppPaths
from ..repositories import stats_repository as stats
from ..utils import ENTERTAINMENT_CATEGORY_KEYS
from .daily_goal_service import GoalStore, build_period_review
from .trusted_metrics_service import assess_range, compare_ranges


def comparison_dates(
    kind: str, dates: list[str], today: date
) -> tuple[list[str], list[str]]:
    completed = [day for day in dates if day < today.isoformat()]
    if not completed:
        return [], []
    first = date.fromisoformat(dates[0])
    if kind == "daily":
        return completed, [(first - timedelta(days=1)).isoformat()]
    if kind == "weekly":
        return completed, [
            (date.fromisoformat(day) - timedelta(days=7)).isoformat()
            for day in completed
        ]
    previous_end = first - timedelta(days=1)
    previous_first = previous_end.replace(day=1)
    if dates[-1] < today.isoformat():
        count = previous_end.day
        return completed, [
            (previous_first + timedelta(days=i)).isoformat() for i in range(count)
        ]
    count = min(len(completed), previous_end.day)
    return completed[:count], [
        (previous_first + timedelta(days=i)).isoformat() for i in range(count)
    ]


def _goals(db_path: str, dates: list[str], rows: list[dict]) -> dict:
    store = GoalStore(AppPaths.from_database(db_path).intelligence_dir)
    try:
        for _attempt in range(2):
            state = store.load()
            has_tasks = any(
                g.get("target_kind") == "task"
                for day in dates
                for g in state["days"].get(day, [])
            )
            assignments = {}
            if has_tasks:
                from .task_decision_service import TaskDecisionStore

                assignments = TaskDecisionStore(store.directory).load()["assignments"]
            result = build_period_review(dates, state, rows, assignments)
            if state["revision"] == store.load()["revision"]:
                return dict(
                    result,
                    status="ready",
                    revision=state["revision"],
                    plan_fingerprint=goal_plan_fingerprint(state, dates),
                )
    except (OSError, RuntimeError, ValueError, KeyError):
        pass
    return {"status": "unavailable", "revision": None, "rows": [], "goal_count": 0}


def goal_plan_fingerprint(state, dates):
    selected = {day: state["days"].get(day, []) for day in dates}
    return hashlib.sha256(
        json.dumps(selected, ensure_ascii=True, sort_keys=True).encode()
    ).hexdigest()


def _half_hours(rows: list[dict]) -> list[dict]:
    """Reuse existing proportional allocation, without filling unknown gaps."""
    from .. import timeline

    result = []
    for day in sorted({row["date"] for row in rows}):
        blocks = timeline._init_blocks()
        for row in rows:
            if row["date"] != day or stats.session_row_is_anomalous(row):
                continue
            try:
                start = datetime.fromisoformat(row["start_time"])
                end = datetime.fromisoformat(row["end_time"])
                if end.date() != start.date() or end <= start:
                    continue
                timeline._distribute_session(
                    blocks,
                    start,
                    end,
                    row["duration_seconds"],
                    row["effective_seconds"],
                    row["engaged_seconds"],
                    row["idle_seconds"],
                    row["process_name"],
                    row["normalized_title"],
                    row["category_key"],
                    row["category_name"],
                    row["session_id"],
                )
            except (ValueError, TypeError, KeyError):
                continue
        for block in blocks:
            if block.effective_seconds or block.idle_seconds:
                timeline._finalise_block(block)
                result.append(
                    {
                        "date": day,
                        "slot": block.slot,
                        "effective_seconds": block.effective_seconds,
                        "idle_seconds": block.idle_seconds,
                        "top_app": block.top_app,
                    }
                )
    return result


def build_context(
    db_path: str, kind: str, dates: list[str], *, now: datetime | None = None
) -> dict:
    if kind not in {"daily", "weekly", "monthly"} or not dates:
        raise ValueError("报告周期无效")
    now = now or datetime.now()
    requested = sorted(set(date.fromisoformat(day).isoformat() for day in dates))
    observed = [day for day in requested if day <= now.date().isoformat()]
    current_dates, previous_dates = comparison_dates(kind, requested, now.date())
    all_dates = sorted(set(observed + previous_dates))
    # A local URI and query_only make writes impossible; BEGIN pins both source
    # reads to the same WAL snapshot. Never use a shared GUI-thread connection.
    conn = sqlite3.connect(
        Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=3
    )
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA query_only=ON")
        conn.execute("BEGIN")
        sessions, legacy = (
            stats._load_mixed_history_rows(
                lambda _p: nullcontext(conn), db_path, all_dates
            )
            if all_dates
            else ([], [])
        )
    finally:
        conn.close()

    def aggregate(days):
        wanted = set(days)
        return stats._aggregate_mixed_history(
            days,
            [r for r in sessions if r["date"] in wanted],
            [r for r in legacy if r["date"] in wanted],
            detail_limit=None,
        )

    payload = aggregate(observed)
    current, previous = aggregate(current_dates), aggregate(previous_dates)
    comparison = compare_ranges(
        assess_range(current["totals"], current_dates),
        assess_range(previous["totals"], previous_dates),
    )
    selected = [
        dict(r, _anomalous=stats.session_row_is_anomalous(r))
        for r in sessions
        if r["date"] in set(observed)
    ]
    selected.sort(key=lambda r: str(r["start_time"]))
    goals = _goals(db_path, observed, selected)
    trust = assess_range(payload["totals"], observed)
    facts = []
    if payload["by_category"] and not payload["totals"]["anomaly_count"]:
        top = payload["by_category"][0]
        facts.append(
            {
                "id": "category:top",
                "type": "category",
                "name": top["category_name"],
                "seconds": top["effective_seconds"],
            }
        )
    if comparison["comparable"] and current_dates and previous_dates:
        facts.append(
            {
                "id": "trend:engaged",
                "type": "trend",
                "before": previous["totals"]["engaged_seconds"],
                "after": current["totals"]["engaged_seconds"],
            }
        )
    actions = []
    for goal in goals["rows"]:
        gap = goal.get("difference_seconds")
        if gap is not None and gap > 0 and goal["evidence_status"] == "ready":
            facts.append(
                {
                    "id": "goal:" + goal["day"] + ":" + goal["title"],
                    "type": "goal",
                    "name": goal["title"],
                    "seconds": gap,
                }
            )
            if not actions:
                actions.append(
                    {
                        "evidence_id": facts[-1]["id"],
                        "name": goal["title"],
                        "seconds": gap,
                    }
                )
    digest_data = {
        "sessions": selected,
        "legacy": [r for r in legacy if r["date"] in set(observed)],
        "goals": goals,
        "dates": requested,
        "observed": observed,
    }
    digest = hashlib.sha256(
        json.dumps(
            digest_data, sort_keys=True, ensure_ascii=False, default=str
        ).encode()
    ).hexdigest()
    valid_times = []
    for value in [r["end_time"] for r in selected] + [
        r["timestamp"] for r in legacy if r["date"] in set(observed)
    ]:
        try:
            datetime.fromisoformat(str(value))
            valid_times.append(str(value))
        except (ValueError, TypeError):
            pass
    last = max(valid_times, default="无有效数据")
    return {
        "format_version": "report-v2",
        "kind": kind,
        "dates": requested,
        "observed_dates": observed,
        "generated_at": now.isoformat(timespec="seconds"),
        "last_record_at": last,
        "ongoing": requested[-1] >= now.date().isoformat(),
        "stats": payload,
        "trust": trust,
        "goals": goals,
        "facts": facts[:3],
        "actions": actions[:1],
        "comparison": dict(
            comparison, current_dates=current_dates, previous_dates=previous_dates
        ),
        "sessions": selected,
        "half_hours": _half_hours(selected) if kind == "daily" else [],
        "native_fingerprint": digest,
        "entertainment_seconds": sum(
            r["effective_seconds"]
            for r in payload["by_category"]
            if r["category_key"] in ENTERTAINMENT_CATEGORY_KEYS
        ),
    }
