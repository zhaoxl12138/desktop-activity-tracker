"""Read-only checks for session data consistency."""

from __future__ import annotations

import shutil
import sqlite3
from datetime import datetime
from pathlib import Path


REPAIR_META_KEY = "legacy_entertainment_idle_repair_v1"
_REPAIRABLE_WHERE = """
switch_reason = 'entertainment_idle'
AND idle_seconds > 0
AND effective_seconds + idle_seconds > duration_seconds + 1
"""


def inspect_data_quality(db_path: str, date_str: str | None = None) -> dict[str, object]:
    """Return consistency issues and a simple confidence score."""
    conn = sqlite3.connect(db_path)
    try:
        where = "WHERE date = ?" if date_str else ""
        args = (date_str,) if date_str else ()
        rows = conn.execute(
            f"SELECT session_id,start_time,end_time,duration_seconds,effective_seconds,idle_seconds "
            f"FROM activity_sessions {where}", args,
        ).fetchall()
        issues: list[dict[str, object]] = []
        seen: set[str] = set()
        for sid, start, end, duration, effective, idle in rows:
            if sid in seen:
                issues.append({"type": "duplicate_session_id", "session_id": sid})
            seen.add(sid)
            duration = int(duration or 0)
            effective = int(effective or 0)
            idle = int(idle or 0)
            if duration < 0 or effective < 0 or idle < 0:
                issues.append({"type": "negative_duration", "session_id": sid})
            if duration + 1 < effective + idle:
                issues.append({"type": "duration_mismatch", "session_id": sid})
            if end < start:
                issues.append({"type": "invalid_time_range", "session_id": sid})
        score = 100 if not rows else max(0, round(100 * (1 - len(issues) / len(rows))))
        return {"checked_sessions": len(rows), "issue_count": len(issues), "score": score, "issues": issues}
    finally:
        conn.close()


def preview_repairable_sessions(db_path: str) -> dict[str, object]:
    """Summarize legacy entertainment-idle rows that are safe to repair."""
    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            f"""
            SELECT date, idle_seconds
            FROM activity_sessions
            WHERE {_REPAIRABLE_WHERE}
            """
        ).fetchall()
        return {
            "repairable_count": len(rows),
            "dates": sorted({str(row[0]) for row in rows}),
            "duplicate_idle_seconds": sum(int(row[1] or 0) for row in rows),
        }
    finally:
        conn.close()


def create_database_backup(db_path: str, reason: str = "manual") -> str:
    """Create a consistent SQLite backup plus optional WAL/SHM recovery files."""
    database_path = Path(db_path).resolve()
    backup_dir = database_path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    safe_reason = "".join(
        character if character.isalnum() or character in {"-", "_"} else "-"
        for character in reason
    ).strip("-") or "manual"
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup_path = backup_dir / (
        f"{database_path.stem}.{timestamp}.before-{safe_reason}.db"
    )

    source = sqlite3.connect(str(database_path))
    destination = sqlite3.connect(str(backup_path))
    try:
        source.execute("PRAGMA busy_timeout=5000")
        source.backup(destination)
    finally:
        destination.close()
        source.close()

    for suffix in ("-wal", "-shm"):
        sidecar = Path(str(database_path) + suffix)
        if sidecar.is_file():
            shutil.copy2(sidecar, Path(str(backup_path) + suffix.replace("-", ".")))
    return str(backup_path)


def repair_legacy_session_data(
    db_path: str,
    reason: str = "manual",
) -> dict[str, object]:
    """Back up and transactionally repair high-confidence legacy rows."""
    preview = preview_repairable_sessions(db_path)
    if not preview["repairable_count"]:
        return {
            **preview,
            "repaired_count": 0,
            "backup_path": "",
        }

    backup_path = create_database_backup(db_path, reason)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            f"""
            UPDATE activity_sessions
            SET idle_seconds = 0
            WHERE {_REPAIRABLE_WHERE}
            """
        )
        remaining = conn.execute(
            f"SELECT COUNT(*) FROM activity_sessions WHERE {_REPAIRABLE_WHERE}"
        ).fetchone()[0]
        if remaining:
            raise RuntimeError(f"legacy session repair left {remaining} rows")
        conn.commit()
        return {
            **preview,
            "repaired_count": int(cursor.rowcount or 0),
            "backup_path": backup_path,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def auto_repair_legacy_sessions(db_path: str) -> dict[str, object]:
    """Run the high-confidence legacy repair once for each database."""
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = ?",
            (REPAIR_META_KEY,),
        ).fetchone()
    finally:
        conn.close()
    if row:
        return {"status": "already_completed", "repaired_count": 0}

    preview = preview_repairable_sessions(db_path)
    if preview["repairable_count"]:
        result = repair_legacy_session_data(db_path, reason="startup")
        status = "repaired"
    else:
        result = {
            **preview,
            "repaired_count": 0,
            "backup_path": "",
        }
        status = "no_changes"

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT OR REPLACE INTO schema_meta(key, value) VALUES (?, ?)",
            (REPAIR_META_KEY, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return {**result, "status": status}
