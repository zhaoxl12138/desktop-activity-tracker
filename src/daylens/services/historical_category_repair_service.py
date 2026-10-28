"""Audited, deterministic repair of recent category labels.

This service never recalculates recorded time.  It only moves explicitly
allow-listed ``other`` sessions to a known category and keeps a full database
backup plus a title-free audit record.
"""

from __future__ import annotations

from datetime import date, datetime
import json
import os
from pathlib import Path
import sqlite3
from typing import Mapping


REPAIR_GROUPS: Mapping[str, dict[str, object]] = {
    "gaming": {
        "category_name": "游戏娱乐",
        "active_rule": "interactive_required",
        "process_names": (
            "LostCastle2.exe", "Lost_Castle.exe", "Brotato.exe",
        ),
    },
    "finance": {
        "category_name": "投资理财",
        "active_rule": "interactive_required",
        "process_names": (
            "hexin.exe", "股票盯盘.exe", "xiadan.exe", "hexinhelper.exe",
        ),
    },
}

_TIME_FIELDS = (
    "duration_seconds", "effective_seconds", "engaged_seconds",
    "passive_seconds", "idle_seconds",
)


def _validate_range(start_day: str, end_day: str) -> tuple[date, date]:
    start = date.fromisoformat(start_day)
    end = date.fromisoformat(end_day)
    if start > end:
        raise ValueError("start_day must not be after end_day")
    if (end - start).days >= 366:
        raise ValueError("repair range must be shorter than 366 days")
    return start, end


def _read_uri(db_path: str) -> str:
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return f"file:{path.as_posix()}?mode=ro"


def _empty_totals() -> dict[str, int]:
    return {field: 0 for field in _TIME_FIELDS}


def _range_time_totals(conn: sqlite3.Connection, start_day: str, end_day: str) -> dict[str, int]:
    fields = ", ".join(f"COALESCE(SUM({field}), 0)" for field in _TIME_FIELDS)
    row = conn.execute(
        f"SELECT {fields} FROM activity_sessions WHERE date BETWEEN ? AND ?",
        (start_day, end_day),
    ).fetchone()
    return {field: int(row[index] or 0) for index, field in enumerate(_TIME_FIELDS)}


def preview_repair(db_path: str, start_day: str, end_day: str) -> dict[str, object]:
    """Return an exact read-only preview of rows eligible for repair."""
    _validate_range(start_day, end_day)
    groups: dict[str, dict[str, object]] = {}
    combined = _empty_totals()
    with sqlite3.connect(_read_uri(db_path), uri=True) as conn:
        for category_key, rule in REPAIR_GROUPS.items():
            processes = tuple(str(value) for value in rule["process_names"])
            placeholders = ",".join("?" for _ in processes)
            fields = ", ".join(
                f"COALESCE(SUM({field}), 0)" for field in _TIME_FIELDS
            )
            row = conn.execute(
                f"""
                SELECT COUNT(*), {fields}
                FROM activity_sessions
                WHERE date BETWEEN ? AND ?
                  AND category_key = 'other'
                  AND lower(process_name) IN ({placeholders})
                """,
                (start_day, end_day, *(process.casefold() for process in processes)),
            ).fetchone()
            totals = {
                field: int(row[index + 1] or 0)
                for index, field in enumerate(_TIME_FIELDS)
            }
            for field, value in totals.items():
                combined[field] += value
            groups[category_key] = {
                "category_name": str(rule["category_name"]),
                "active_rule": str(rule["active_rule"]),
                "process_names": list(processes),
                "rows": int(row[0] or 0),
                "time_totals": totals,
            }
    return {
        "start_day": start_day,
        "end_day": end_day,
        "groups": groups,
        "total_rows": sum(int(group["rows"]) for group in groups.values()),
        "time_totals": combined,
    }


def _backup_database(db_path: Path, backup_path: Path) -> None:
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as source, sqlite3.connect(backup_path) as target:
        source.backup(target)


def _merge_rule_processes(
    conn: sqlite3.Connection,
    category_key: str,
    rule: Mapping[str, object],
) -> None:
    row = conn.execute(
        "SELECT process_names FROM custom_rules WHERE category_key = ?",
        (category_key,),
    ).fetchone()
    existing = [
        line.strip() for line in str(row[0] if row else "").splitlines()
        if line.strip()
    ]
    seen = {value.casefold() for value in existing}
    for process in rule["process_names"]:
        value = str(process)
        if value.casefold() not in seen:
            existing.append(value)
            seen.add(value.casefold())
    process_names = "\n".join(existing)
    if row is None:
        conn.execute(
            """
            INSERT INTO custom_rules
                (category_key, display_name, active_rule, process_names,
                 title_keywords, title_patterns, process_names_mode,
                 title_keywords_mode, title_patterns_mode)
            VALUES (?, ?, ?, ?, '', '', 'replace', 'inherit', 'inherit')
            """,
            (
                category_key, str(rule["category_name"]),
                str(rule["active_rule"]), process_names,
            ),
        )
    else:
        conn.execute(
            """
            UPDATE custom_rules
            SET display_name = ?, active_rule = ?, process_names = ?,
                process_names_mode = 'replace'
            WHERE category_key = ?
            """,
            (
                str(rule["category_name"]), str(rule["active_rule"]),
                process_names, category_key,
            ),
        )


def _write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def apply_repair(
    db_path: str,
    start_day: str,
    end_day: str,
    *,
    backup_dir: str | Path | None = None,
    audit_dir: str | Path | None = None,
    timestamp: str | None = None,
) -> dict[str, object]:
    """Back up and transactionally apply the deterministic repair."""
    _validate_range(start_day, end_day)
    path = Path(db_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    stamp = timestamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = Path(backup_dir) if backup_dir is not None else path.parent / "backups"
    audit_root = Path(audit_dir) if audit_dir is not None else path.parent / "logs"
    backup_path = backup_root / f"usage-before-category-repair-{stamp}.db"
    audit_path = audit_root / f"category-repair-{stamp}.json"
    if backup_path.exists() or audit_path.exists():
        raise FileExistsError(f"repair output already exists for timestamp {stamp}")

    preview = preview_repair(str(path), start_day, end_day)
    _backup_database(path, backup_path)
    changed_rows = 0
    with sqlite3.connect(path) as conn:
        before_totals = _range_time_totals(conn, start_day, end_day)
        try:
            conn.execute("BEGIN IMMEDIATE")
            for category_key, rule in REPAIR_GROUPS.items():
                processes = tuple(str(value) for value in rule["process_names"])
                placeholders = ",".join("?" for _ in processes)
                cursor = conn.execute(
                    f"""
                    UPDATE activity_sessions
                    SET category_key = ?, category_name = ?, active_rule = ?
                    WHERE date BETWEEN ? AND ?
                      AND category_key = 'other'
                      AND lower(process_name) IN ({placeholders})
                    """,
                    (
                        category_key, str(rule["category_name"]),
                        str(rule["active_rule"]), start_day, end_day,
                        *(process.casefold() for process in processes),
                    ),
                )
                changed_rows += max(0, int(cursor.rowcount))
                _merge_rule_processes(conn, category_key, rule)
            after_totals = _range_time_totals(conn, start_day, end_day)
            if before_totals != after_totals:
                raise RuntimeError("category repair changed recorded time totals")
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    audit: dict[str, object] = {
        "operation": "deterministic_recent_category_repair",
        "timestamp": stamp,
        "database": str(path),
        "backup_path": str(backup_path.resolve()),
        "start_day": start_day,
        "end_day": end_day,
        "groups": preview["groups"],
        "preview_rows": preview["total_rows"],
        "changed_rows": changed_rows,
        "time_totals_before": before_totals,
        "time_totals_after": after_totals,
        "time_conserved": before_totals == after_totals,
    }
    _write_json_atomic(audit_path, audit)
    return {
        **audit,
        "audit_path": str(audit_path.resolve()),
    }
