"""Apply adopted high-confidence AI classifications to today's fallback rows."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from ..category_registry import category_definition
from ..classifier import _DEFAULT_BROWSER_PROCESSES
from ..session_tracker import normalize_window_title
from .classification_correction_service import move_process_rule
from .intelligence_state import atomic_json


_FALLBACK_CATEGORIES = ("other", "browser_general")
_TIME_FIELDS = (
    "duration_seconds",
    "effective_seconds",
    "engaged_seconds",
    "passive_seconds",
    "idle_seconds",
)


@dataclass(frozen=True)
class AiBackfillResult:
    updated_sessions: int
    updated_effective_seconds: int
    rule_changed: bool
    shared_browser: bool
    time_conserved: bool
    audit_path: str


def _title_key(value: object) -> str:
    return " ".join(str(value or "").split()).casefold()


def _row_title_key(row: sqlite3.Row) -> str:
    normalized = str(row["normalized_title"] or "").strip()
    if not normalized:
        normalized = normalize_window_title(
            str(row["process_name"] or ""),
            str(row["window_title"] or ""),
        )
    return _title_key(normalized)


def _time_totals(rows: list[sqlite3.Row]) -> dict[str, int]:
    return {
        field: sum(int(row[field] or 0) for row in rows)
        for field in _TIME_FIELDS
    }


def _timeline(rows: list[sqlite3.Row]) -> dict[int, tuple[object, ...]]:
    return {
        int(row["id"]): (
            row["start_time"],
            row["end_time"],
            *(int(row[field] or 0) for field in _TIME_FIELDS),
        )
        for row in rows
    }


def apply_ai_classification_backfill(
    *,
    db_path: str,
    process_name: str,
    window_title: str,
    normalized_title: str,
    category_key: str,
    categories: dict | None,
    day: date | str | None = None,
) -> AiBackfillResult:
    """Backfill exact-title fallbacks and promote desktop processes atomically."""
    process = str(process_name or "").strip()
    raw_title = str(window_title or "").strip()
    wanted_title = str(normalized_title or "").strip()
    if not wanted_title:
        wanted_title = normalize_window_title(process, raw_title)
    if not process or not raw_title or not wanted_title:
        raise ValueError("应用和标题不能为空")
    definition = category_definition(category_key, categories)
    if definition is None:
        raise ValueError("不支持的分类")
    selected_day = (
        day.isoformat()
        if isinstance(day, date)
        else str(day or date.today().isoformat())
    )
    shared_browser = process.casefold() in _DEFAULT_BROWSER_PROCESSES
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    audit_path = (
        Path(db_path).resolve().parent
        / "logs"
        / f"ai-classification-backfill-{stamp}.json"
    )
    audit_written = False

    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN IMMEDIATE")
        try:
            candidates = list(conn.execute(
                """
                SELECT * FROM activity_sessions
                WHERE date = ? AND lower(process_name) = lower(?)
                ORDER BY id
                """,
                (selected_day, process),
            ))
            matches = [
                row for row in candidates
                if _row_title_key(row) == _title_key(wanted_title)
            ]
            before_totals = _time_totals(matches)
            before_timeline = _timeline(matches)
            changed_rows = [
                row for row in matches
                if (
                    str(row["category_key"] or "") in _FALLBACK_CATEGORIES
                    and not str(row["classification_version"] or "").startswith(
                        "manual-"
                    )
                )
            ]
            if changed_rows:
                placeholders = ",".join("?" for _ in changed_rows)
                conn.execute(
                    f"""
                    UPDATE activity_sessions
                    SET category_key = ?, category_name = ?, active_rule = ?,
                        classification_version = 'ai-high-backfill-v1'
                    WHERE id IN ({placeholders})
                    """,
                    (
                        definition.id,
                        definition.name,
                        definition.timing_policy,
                        *(int(row["id"]) for row in changed_rows),
                    ),
                )
            rule_changed = False
            if not shared_browser:
                rule_changed, _snapshot = move_process_rule(
                    conn,
                    process,
                    definition.id,
                    definition.name,
                    definition.timing_policy,
                )
            refreshed_candidates = list(conn.execute(
                """
                SELECT * FROM activity_sessions
                WHERE date = ? AND lower(process_name) = lower(?)
                ORDER BY id
                """,
                (selected_day, process),
            ))
            refreshed = [
                row for row in refreshed_candidates
                if _row_title_key(row) == _title_key(wanted_title)
            ]
            if (
                before_totals != _time_totals(refreshed)
                or before_timeline != _timeline(refreshed)
            ):
                raise RuntimeError("AI分类回填改变了记录时间")

            updated_effective = sum(
                int(row["effective_seconds"] or 0) for row in changed_rows
            )
            audit = {
                "operation": "ai_high_confidence_backfill",
                "timestamp": stamp,
                "date": selected_day,
                "process_name": process,
                "category_key": definition.id,
                "category_name": definition.name,
                "updated_sessions": len(changed_rows),
                "updated_effective_seconds": updated_effective,
                "rule_changed": rule_changed,
                "shared_browser": shared_browser,
                "time_totals": before_totals,
                "time_conserved": True,
            }
            atomic_json(audit_path, audit)
            audit_written = True
            conn.commit()
        except Exception:
            conn.rollback()
            if audit_written:
                audit_path.unlink(missing_ok=True)
            raise

    return AiBackfillResult(
        updated_sessions=len(changed_rows),
        updated_effective_seconds=updated_effective,
        rule_changed=rule_changed,
        shared_browser=shared_browser,
        time_conserved=True,
        audit_path=str(audit_path),
    )


def result_payload(result: AiBackfillResult) -> dict[str, object]:
    return asdict(result)
