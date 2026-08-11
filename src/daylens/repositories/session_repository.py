"""Session and log write helpers split from the legacy database module."""

from __future__ import annotations


def insert_activity_log(conn, sample: dict) -> None:
    sql = """
    INSERT INTO activity_logs
        (timestamp, date, process_name, exe_path, window_title,
         category_key, category_name, active_rule,
         is_user_active, is_effective, idle_seconds, duration_seconds)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(
        sql,
        (
            sample["timestamp"],
            sample["date"],
            sample.get("process_name", ""),
            sample.get("exe_path", ""),
            sample.get("window_title", ""),
            sample.get("category_key", ""),
            sample.get("category_name", ""),
            sample.get("active_rule", ""),
            1 if sample.get("is_user_active") else 0,
            1 if sample.get("is_effective") else 0,
            sample.get("idle_seconds", 0),
            sample.get("duration_seconds", 0),
        ),
    )
    conn.commit()


def insert_session(conn, session, maybe_checkpoint=lambda conn: None) -> int:
    sql = """
    INSERT OR REPLACE INTO activity_sessions
        (session_id, start_time, end_time, date, process_name, exe_path,
         window_title, normalized_title, category_key, category_name,
         active_rule, duration_seconds, effective_seconds, idle_seconds,
         switch_reason, engaged_seconds, passive_seconds, metric_version,
         classification_version)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cur = conn.execute(
        sql,
        (
            session.session_id,
            session.start_time.strftime("%Y-%m-%d %H:%M:%S"),
            session.end_time.strftime("%Y-%m-%d %H:%M:%S"),
            session.date,
            session.process_name,
            session.exe_path,
            session.window_title,
            session.normalized_title,
            session.category_key,
            session.category_name,
            session.active_rule,
            session.duration_seconds,
            session.effective_seconds,
            session.idle_seconds,
            session.switch_reason,
            session.engaged_seconds,
            session.passive_seconds,
            session.metric_version,
            session.classification_version,
        ),
    )
    conn.commit()
    maybe_checkpoint(conn)
    return cur.lastrowid


def update_session(conn, session, maybe_checkpoint=lambda conn: None) -> None:
    sql = """
    UPDATE activity_sessions SET
        end_time = ?,
        duration_seconds = ?,
        effective_seconds = ?,
        idle_seconds = ?,
        switch_reason = ?,
        engaged_seconds = ?,
        passive_seconds = ?,
        metric_version = ?,
        classification_version = ?
    WHERE session_id = ?
    """
    conn.execute(
        sql,
        (
            session.end_time.strftime("%Y-%m-%d %H:%M:%S"),
            session.duration_seconds,
            session.effective_seconds,
            session.idle_seconds,
            session.switch_reason or "",
            session.engaged_seconds,
            session.passive_seconds,
            session.metric_version,
            session.classification_version,
            session.session_id,
        ),
    )
    conn.commit()
    maybe_checkpoint(conn)
