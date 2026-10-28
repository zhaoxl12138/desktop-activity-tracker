"""Apply one manual classification decision consistently across local state."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

from ..category_registry import category_definition
from ..classifier import _DEFAULT_BROWSER_PROCESSES
from ..session_tracker import normalize_window_title
from .intelligence_state import atomic_json, save_override


_TIME_FIELDS = (
    "duration_seconds",
    "effective_seconds",
    "engaged_seconds",
    "passive_seconds",
    "idle_seconds",
)
_RULE_COLUMNS = (
    "category_key",
    "display_name",
    "active_rule",
    "process_names",
    "title_keywords",
    "title_patterns",
    "process_names_mode",
    "title_keywords_mode",
    "title_patterns_mode",
)


@dataclass(frozen=True)
class CorrectionResult:
    updated_sessions: int
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


def _rule_values(row: sqlite3.Row | dict) -> tuple[object, ...]:
    return tuple(row[column] for column in _RULE_COLUMNS)


def _upsert_rule(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """
        INSERT INTO custom_rules (
            category_key, display_name, active_rule, process_names,
            title_keywords, title_patterns, process_names_mode,
            title_keywords_mode, title_patterns_mode
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(category_key) DO UPDATE SET
            display_name = excluded.display_name,
            active_rule = excluded.active_rule,
            process_names = excluded.process_names,
            title_keywords = excluded.title_keywords,
            title_patterns = excluded.title_patterns,
            process_names_mode = excluded.process_names_mode,
            title_keywords_mode = excluded.title_keywords_mode,
            title_patterns_mode = excluded.title_patterns_mode
        """,
        _rule_values(row),
    )


def move_process_rule(
    conn: sqlite3.Connection,
    process_name: str,
    category_key: str,
    category_name: str,
    active_rule: str,
) -> tuple[bool, dict[str, dict | None]]:
    rows = {
        str(row["category_key"]): dict(row)
        for row in conn.execute("SELECT * FROM custom_rules")
    }
    folded = process_name.casefold()
    affected = {
        key
        for key, row in rows.items()
        if any(item.casefold() == folded for item in str(row["process_names"] or "").splitlines())
    }
    affected.add(category_key)
    before = {key: dict(rows[key]) if key in rows else None for key in affected}

    changed = False
    for key, row in rows.items():
        if key == category_key:
            continue
        original = [item for item in str(row["process_names"] or "").splitlines() if item]
        kept = [item for item in original if item.casefold() != folded]
        if kept != original:
            row["process_names"] = "\n".join(kept)
            _upsert_rule(conn, row)
            changed = True

    target = rows.get(category_key)
    if target is None:
        target = {
            "category_key": category_key,
            "display_name": category_name,
            "active_rule": active_rule,
            "process_names": process_name,
            "title_keywords": "",
            "title_patterns": "",
            "process_names_mode": "inherit",
            "title_keywords_mode": "inherit",
            "title_patterns_mode": "inherit",
        }
        changed = True
    else:
        names = [item for item in str(target["process_names"] or "").splitlines() if item]
        if not any(item.casefold() == folded for item in names):
            names.append(process_name)
            target["process_names"] = "\n".join(names)
            changed = True
        if target["display_name"] != category_name:
            target["display_name"] = category_name
            changed = True
        if target["active_rule"] != active_rule:
            target["active_rule"] = active_rule
            changed = True
    _upsert_rule(conn, target)
    return changed, before


def _restore_database(
    db_path: str,
    session_snapshot: dict[int, tuple[object, ...]],
    rule_snapshot: dict[str, dict | None],
) -> None:
    with sqlite3.connect(db_path, timeout=5) as conn:
        conn.execute("BEGIN IMMEDIATE")
        for identity, values in session_snapshot.items():
            conn.execute(
                """
                UPDATE activity_sessions
                SET category_key = ?, category_name = ?, active_rule = ?,
                    classification_version = ?
                WHERE id = ?
                """,
                (*values, identity),
            )
        for key, row in rule_snapshot.items():
            if row is None:
                conn.execute("DELETE FROM custom_rules WHERE category_key = ?", (key,))
            else:
                _upsert_rule(conn, row)
        conn.commit()


def apply_classification_correction(
    *,
    db_path: str,
    intelligence_dir: str | Path,
    process_name: str,
    window_title: str,
    normalized_title: str,
    category_key: str,
    categories: dict | None,
    day: date | str | None = None,
    scope: str = "similar",
) -> CorrectionResult:
    """Apply one correction without changing any recorded time value."""
    process = str(process_name or "").strip()
    raw_title = str(window_title or "").strip()
    wanted_title = str(normalized_title or "").strip()
    if not wanted_title:
        wanted_title = normalize_window_title(process, raw_title)
    if not process or not raw_title or not wanted_title:
        raise ValueError("应用和标题不能为空")
    definition = category_definition(category_key, categories)
    if definition is None or not definition.manual_allowed:
        raise ValueError("不支持的分类")
    selected_day = day.isoformat() if isinstance(day, date) else str(day or date.today().isoformat())
    shared_browser = process.casefold() in _DEFAULT_BROWSER_PROCESSES
    changed_rows: list[sqlite3.Row] = []
    session_snapshot: dict[int, tuple[object, ...]] = {}
    rule_snapshot: dict[str, dict | None] = {}
    rule_changed = False

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
            matches = [row for row in candidates if _row_title_key(row) == _title_key(wanted_title)]
            before_totals = _time_totals(matches)
            changed_rows = [
                row for row in matches
                if (
                    str(row["category_key"] or "") != definition.id
                    or str(row["category_name"] or "") != definition.name
                    or str(row["active_rule"] or "") != definition.timing_policy
                    or str(row["classification_version"] or "") != "manual-correction-v1"
                )
            ]
            session_snapshot = {
                int(row["id"]): (
                    row["category_key"], row["category_name"],
                    row["active_rule"], row["classification_version"],
                )
                for row in changed_rows
            }
            if changed_rows:
                placeholders = ",".join("?" for _ in changed_rows)
                conn.execute(
                    f"""
                    UPDATE activity_sessions
                    SET category_key = ?, category_name = ?, active_rule = ?,
                        classification_version = 'manual-correction-v1'
                    WHERE id IN ({placeholders})
                    """,
                    (
                        definition.id, definition.name, definition.timing_policy,
                        *(int(row["id"]) for row in changed_rows),
                    ),
                )
            if not shared_browser:
                rule_changed, rule_snapshot = move_process_rule(
                    conn, process, definition.id, definition.name,
                    definition.timing_policy,
                )
            refreshed = list(conn.execute(
                """
                SELECT * FROM activity_sessions
                WHERE date = ? AND lower(process_name) = lower(?)
                ORDER BY id
                """,
                (selected_day, process),
            ))
            after_matches = [row for row in refreshed if _row_title_key(row) == _title_key(wanted_title)]
            if before_totals != _time_totals(after_matches):
                raise RuntimeError("分类纠错改变了记录时长")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    audit_path = Path(db_path).resolve().parent / "logs" / f"classification-correction-{stamp}.json"
    audit = {
        "operation": "manual_classification_correction",
        "timestamp": stamp,
        "date": selected_day,
        "process_name": process,
        "category_key": definition.id,
        "category_name": definition.name,
        "updated_sessions": len(changed_rows),
        "rule_changed": rule_changed,
        "shared_browser": shared_browser,
        "time_totals": before_totals,
        "time_conserved": True,
    }
    atomic_json(audit_path, audit)
    try:
        save_override(
            intelligence_dir, process, raw_title, definition.id,
            scope=scope, categories=categories,
        )
    except Exception:
        try:
            _restore_database(db_path, session_snapshot, rule_snapshot)
        finally:
            audit_path.unlink(missing_ok=True)
        raise
    return CorrectionResult(
        updated_sessions=len(changed_rows),
        rule_changed=rule_changed,
        shared_browser=shared_browser,
        time_conserved=True,
        audit_path=str(audit_path),
    )


def result_payload(result: CorrectionResult) -> dict[str, object]:
    return asdict(result)
