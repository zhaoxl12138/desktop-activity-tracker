"""Read-only checks for session data consistency."""

from __future__ import annotations

import sqlite3


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
