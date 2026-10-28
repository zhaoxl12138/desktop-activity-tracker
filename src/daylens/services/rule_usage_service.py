"""Read-only usage snapshot for the rule-management page."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from types import MappingProxyType
from typing import Mapping


@dataclass(frozen=True)
class RuleProcessUsage:
    process_name: str
    source: str
    hits: int = 0
    effective_seconds: int = 0
    last_seen: str = ""


@dataclass(frozen=True)
class RuleCategoryUsage:
    visible_processes: tuple[RuleProcessUsage, ...]
    hidden_factory_count: int
    hits: int
    effective_seconds: int
    last_seen: str


@dataclass(frozen=True)
class RuleUsageSnapshot:
    categories: Mapping[str, RuleCategoryUsage]
    has_history: bool
    degraded: bool = False


def _unique_processes(category: dict) -> list[str]:
    processes = (category.get("match") or {}).get("process_names") or []
    result: list[str] = []
    seen: set[str] = set()
    for raw in processes:
        process = str(raw).strip()
        key = process.casefold()
        if not process or key in seen:
            continue
        seen.add(key)
        result.append(process)
    return result


def _usage_rows(
    db_path: str, *, start_day: str, end_day: str
) -> tuple[bool, dict[str, dict[str, int | str]]]:
    with sqlite3.connect(db_path, timeout=2) as conn:
        has_history = conn.execute(
            "SELECT EXISTS(SELECT 1 FROM activity_sessions LIMIT 1)"
        ).fetchone()[0] == 1
        rows = conn.execute(
            """
            SELECT lower(process_name) AS process_key,
                   count(*) AS hits,
                   sum(coalesce(effective_seconds, 0)) AS effective_seconds,
                   max(date) AS last_seen
            FROM activity_sessions
            WHERE date >= ? AND date <= ? AND trim(coalesce(process_name, '')) <> ''
            GROUP BY lower(process_name)
            """,
            (start_day, end_day),
        ).fetchall()
    return has_history, {
        str(row[0]).casefold(): {
            "hits": int(row[1] or 0),
            "effective_seconds": int(row[2] or 0),
            "last_seen": str(row[3] or ""),
        }
        for row in rows
    }


def load_rule_usage_snapshot(
    db_path: str,
    categories: dict[str, dict],
    factory_categories: dict[str, dict],
    *,
    days: int = 30,
    today: date | None = None,
) -> RuleUsageSnapshot:
    """Return visible rule applications without changing persisted rules."""
    end = today or date.today()
    start = end - timedelta(days=max(1, int(days)) - 1)
    degraded = False
    try:
        has_history, recent = _usage_rows(
            db_path, start_day=start.isoformat(), end_day=end.isoformat()
        )
    except (OSError, sqlite3.Error):
        has_history = False
        recent = {}
        degraded = True

    summaries: dict[str, RuleCategoryUsage] = {}
    for category_key, category in categories.items():
        factory_keys = {
            process.casefold()
            for process in _unique_processes(factory_categories.get(category_key, {}))
        }
        visible: list[RuleProcessUsage] = []
        hidden_factory_count = 0
        for process in _unique_processes(category):
            key = process.casefold()
            stats = recent.get(key)
            learned = key not in factory_keys
            if has_history and stats is None and not learned and not degraded:
                hidden_factory_count += 1
                continue
            source = "recent" if stats is not None else ("learned" if learned else "factory")
            visible.append(
                RuleProcessUsage(
                    process_name=process,
                    source=source,
                    hits=int((stats or {}).get("hits", 0)),
                    effective_seconds=int((stats or {}).get("effective_seconds", 0)),
                    last_seen=str((stats or {}).get("last_seen", "")),
                )
            )

        summaries[category_key] = RuleCategoryUsage(
            visible_processes=tuple(visible),
            hidden_factory_count=hidden_factory_count,
            hits=sum(item.hits for item in visible),
            effective_seconds=sum(item.effective_seconds for item in visible),
            last_seen=max((item.last_seen for item in visible), default=""),
        )

    return RuleUsageSnapshot(
        categories=MappingProxyType(summaries),
        has_history=has_history,
        degraded=degraded,
    )

