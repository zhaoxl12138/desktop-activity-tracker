"""SQLite database operations for activity logs and sessions."""

import os
import sqlite3
from datetime import datetime, timedelta

from . import get_app_root

# Process names of the tracker itself — excluded from all queries
_SELF_PROCS = {"daylens.exe", "daylens-debug.exe", "desktop-activity-tracker.exe"}

_WAL_CHECKPOINT_INTERVAL = 100  # commits between WAL checkpoints


class _TrackedConnection(sqlite3.Connection):
    """SQLite connection subclass that can keep lightweight runtime state."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS activity_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    date TEXT NOT NULL,
    process_name TEXT,
    exe_path TEXT,
    window_title TEXT,
    category_key TEXT,
    category_name TEXT,
    active_rule TEXT,
    is_user_active INTEGER,
    is_effective INTEGER,
    idle_seconds REAL,
    duration_seconds INTEGER
);

CREATE TABLE IF NOT EXISTS activity_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    date TEXT NOT NULL,
    process_name TEXT,
    exe_path TEXT,
    window_title TEXT,
    normalized_title TEXT,
    category_key TEXT,
    category_name TEXT,
    active_rule TEXT,
    duration_seconds INTEGER DEFAULT 0,
    effective_seconds INTEGER DEFAULT 0,
    idle_seconds INTEGER DEFAULT 0,
    switch_reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS daily_summary (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    category_key TEXT,
    category_name TEXT,
    process_name TEXT,
    total_seconds INTEGER,
    effective_seconds INTEGER,
    idle_seconds INTEGER
);

CREATE INDEX IF NOT EXISTS idx_activity_date ON activity_logs(date);
CREATE INDEX IF NOT EXISTS idx_activity_category ON activity_logs(category_key);
CREATE INDEX IF NOT EXISTS idx_sessions_date ON activity_sessions(date);
CREATE INDEX IF NOT EXISTS idx_sessions_category ON activity_sessions(category_key);
CREATE INDEX IF NOT EXISTS idx_sessions_session_id ON activity_sessions(session_id);
"""


def _wal_checkpoint(conn):
    """Integrate WAL into main database, preventing unbounded growth."""
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    except sqlite3.OperationalError:
        pass  # WAL may not exist yet


def _recover_stale_wal(db_path):
    """If a WAL file exists but no writer is active, integrate it."""
    wal_path = db_path + "-wal"
    if not os.path.exists(wal_path):
        return
    try:
        conn = sqlite3.connect(db_path)
        conn.execute("PRAGMA journal_mode=WAL")
        rows = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        if rows:
            busy, _, _ = rows
            if busy == 0:
                conn.close()
    except sqlite3.OperationalError:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def get_db_path(config):
    db_path = config.get("db_path", "data/usage.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(get_app_root(), db_path)
    return db_path


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    _recover_stale_wal(db_path)
    conn = sqlite3.connect(db_path, factory=_TrackedConnection)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(SCHEMA)
    conn.commit()
    conn._commit_count = 0
    return conn


def close_db(conn):
    """Safely close a database connection, checkpointing WAL first."""
    if conn is None:
        return
    try:
        _wal_checkpoint(conn)
        conn.close()
    except Exception:
        pass


# ── Legacy log-level insert (kept for backward compat, not used by v1.1+) ──

def insert_activity_log(conn, sample):
    sql = """
    INSERT INTO activity_logs
        (timestamp, date, process_name, exe_path, window_title,
         category_key, category_name, active_rule,
         is_user_active, is_effective, idle_seconds, duration_seconds)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    conn.execute(sql, (
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
    ))
    conn.commit()


# ── Session-level operations (v1.1+) ──

def insert_session(conn, session):
    """Insert a new activity_session and return its row id."""
    sql = """
    INSERT OR REPLACE INTO activity_sessions
        (session_id, start_time, end_time, date, process_name, exe_path,
         window_title, normalized_title, category_key, category_name,
         active_rule, duration_seconds, effective_seconds, idle_seconds,
         switch_reason)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    cur = conn.execute(sql, (
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
    ))
    conn.commit()
    _maybe_checkpoint(conn)
    return cur.lastrowid


def update_session(conn, session):
    """Update an existing activity_session record (mid-session flush)."""
    sql = """
    UPDATE activity_sessions SET
        end_time = ?,
        duration_seconds = ?,
        effective_seconds = ?,
        idle_seconds = ?,
        switch_reason = ?
    WHERE session_id = ?
    """
    conn.execute(sql, (
        session.end_time.strftime("%Y-%m-%d %H:%M:%S"),
        session.duration_seconds,
        session.effective_seconds,
        session.idle_seconds,
        session.switch_reason or "",
        session.session_id,
    ))
    conn.commit()
    _maybe_checkpoint(conn)


def _maybe_checkpoint(conn):
    """Checkpoint WAL every N commits to prevent unbounded growth."""
    conn._commit_count = getattr(conn, '_commit_count', 0) + 1
    if conn._commit_count % _WAL_CHECKPOINT_INTERVAL == 0:
        _wal_checkpoint(conn)


# ── Deprecated raw log queries (for backward compat) ──

def query_date(db_path, date_str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_logs WHERE date = ? ORDER BY timestamp",
        (date_str,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _query_date_stats_from_logs(db_path, date_str):
    """Old per-sample stats query (fallback for pre-v1.1 data)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    totals = conn.execute("""
        SELECT
            COUNT(*) as total_samples,
            SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
            SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
            SUM(duration_seconds) as total_seconds
        FROM activity_logs WHERE date = ?
    """, (date_str,)).fetchone()

    by_category = conn.execute("""
        SELECT
            category_key,
            category_name,
            SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
            SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
            SUM(duration_seconds) as total_seconds
        FROM activity_logs WHERE date = ?
        GROUP BY category_key, category_name
        ORDER BY effective_seconds DESC
    """, (date_str,)).fetchall()

    by_app = conn.execute("""
        SELECT
            process_name,
            window_title,
            category_key,
            category_name,
            SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
            COUNT(*) as samples
        FROM activity_logs WHERE date = ? AND is_effective = 1
        GROUP BY process_name, category_key
        ORDER BY effective_seconds DESC
    """, (date_str,)).fetchall()

    by_app_detail = conn.execute("""
        SELECT
            process_name,
            window_title,
            SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds
        FROM activity_logs WHERE date = ? AND is_effective = 1
        GROUP BY process_name, window_title
        ORDER BY effective_seconds DESC
        LIMIT 50
    """, (date_str,)).fetchall()

    conn.close()
    return {
        "totals": dict(totals),
        "by_category": [dict(r) for r in by_category],
        "by_app": _filter_self([dict(r) for r in by_app]),
        "by_app_detail": _filter_self([dict(r) for r in by_app_detail]),
    }


def _filter_self(rows):
    """Remove rows where process_name is the tracker itself."""
    return [r for r in rows if not r.get("process_name", "").lower().startswith("daylens")]



# ── Session-based queries (v1.1+) ──

def _query_date_stats_from_sessions(db_path, date_str):
    """Aggregated stats from activity_sessions table."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    totals = conn.execute("""
        SELECT
            COUNT(*) as total_samples,
            SUM(effective_seconds) as effective_seconds,
            SUM(idle_seconds) as idle_seconds,
            SUM(duration_seconds) as total_seconds
        FROM activity_sessions WHERE date = ?
    """, (date_str,)).fetchone()

    by_category = conn.execute("""
        SELECT
            category_key,
            category_name,
            SUM(effective_seconds) as effective_seconds,
            SUM(idle_seconds) as idle_seconds,
            SUM(duration_seconds) as total_seconds
        FROM activity_sessions WHERE date = ?
        GROUP BY category_key, category_name
        ORDER BY effective_seconds DESC
    """, (date_str,)).fetchall()

    by_app = conn.execute("""
        SELECT
            process_name,
            normalized_title as window_title,
            category_key,
            category_name,
            SUM(effective_seconds) as effective_seconds,
            COUNT(*) as samples
        FROM activity_sessions WHERE date = ? AND effective_seconds > 0
        GROUP BY process_name, category_key
        ORDER BY effective_seconds DESC
    """, (date_str,)).fetchall()

    by_app_detail = conn.execute("""
        SELECT
            process_name,
            normalized_title as window_title,
            SUM(effective_seconds) as effective_seconds
        FROM activity_sessions WHERE date = ? AND effective_seconds > 0
        GROUP BY process_name, normalized_title
        ORDER BY effective_seconds DESC
        LIMIT 50
    """, (date_str,)).fetchall()

    conn.close()
    return {
        "totals": dict(totals),
        "by_category": [dict(r) for r in by_category],
        "by_app": _filter_self([dict(r) for r in by_app]),
        "by_app_detail": _filter_self([dict(r) for r in by_app_detail]),
    }


def query_date_stats(db_path, date_str):
    """Return aggregated stats for a given date.

    Prefers activity_sessions table; falls back to old activity_logs if
    no session data exists.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM activity_sessions WHERE date = ?",
        (date_str,)
    ).fetchone()
    conn.close()

    if row and row["cnt"] > 0:
        return _query_date_stats_from_sessions(db_path, date_str)
    return _query_date_stats_from_logs(db_path, date_str)


def query_session_entertainment_trend(db_path, days=3):
    """Return entertainment seconds for the last N days from activity_sessions."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    dates.reverse()

    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(f"""
        SELECT date,
               SUM(effective_seconds) as entertainment_seconds
        FROM activity_sessions
        WHERE date IN ({placeholders}) AND category_key = 'video'
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()

    conn.close()

    result_map = {r["date"]: r["entertainment_seconds"] or 0 for r in rows}
    return [{"date": d, "entertainment_seconds": result_map.get(d, 0)} for d in dates]


def query_entertainment_trend(db_path, days=3):
    """Return entertainment seconds for the last N days.

    Prefers activity_sessions if data exists, falls back to old logs.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT COUNT(*) as cnt FROM activity_sessions").fetchone()
    conn.close()

    if row and row["cnt"] > 0:
        return query_session_entertainment_trend(db_path, days)

    # Fallback to old logs
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    dates.reverse()

    placeholders = ",".join("?" * len(dates))
    rows = conn.execute(f"""
        SELECT date,
               SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as entertainment_seconds
        FROM activity_logs
        WHERE date IN ({placeholders}) AND category_key = 'video'
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()
    conn.close()

    result_map = {r["date"]: r["entertainment_seconds"] or 0 for r in rows}
    return [{"date": d, "entertainment_seconds": result_map.get(d, 0)} for d in dates]


def query_session_count(db_path, date_str):
    """Return the number of sessions for a given date (used as switch count)."""
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM activity_sessions WHERE date = ?",
        (date_str,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def query_today_sessions(db_path, date_str):
    """Return all activity_sessions for a date, ordered by start_time."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT session_id, start_time, end_time, process_name,
                  normalized_title, category_key, category_name,
                  duration_seconds, effective_seconds, idle_seconds
           FROM activity_sessions
           WHERE date = ?
           ORDER BY start_time""",
        (date_str,)
    ).fetchall()
    conn.close()
    return _filter_self([dict(r) for r in rows])


def count_consecutive_days(db_path):
    """Return consecutive days (including today) with activity data."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT DISTINCT date FROM activity_sessions ORDER BY date DESC"
    ).fetchall()
    conn.close()

    if not rows:
        return 0

    dates = [r["date"] for r in rows]
    today = datetime.now().strftime("%Y-%m-%d")
    if dates[0] != today:
        return 0

    count = 1
    for i in range(1, len(dates)):
        d1 = datetime.strptime(dates[i - 1], "%Y-%m-%d")
        d2 = datetime.strptime(dates[i], "%Y-%m-%d")
        if (d1 - d2).days == 1:
            count += 1
        else:
            break
    return count


def query_date_range_stats(db_path, dates):
    """Return per-day and aggregated stats for a range of dates.

    Prefers activity_sessions table; falls back to old activity_logs if
    no session data exists.
    """
    if not dates:
        return {"dates": [], "daily": [], "by_category": [], "by_app": [], "totals": {}}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT COUNT(*) as cnt FROM activity_sessions").fetchone()
    conn.close()

    if row and row["cnt"] > 0:
        return _query_date_range_from_sessions(db_path, dates)
    return _query_date_range_from_logs(db_path, dates)


def _query_date_range_from_sessions(db_path, dates):
    """Per-day + aggregated stats from activity_sessions."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(dates))

    daily_rows = conn.execute(f"""
        SELECT date,
               SUM(effective_seconds) as effective_seconds,
               SUM(idle_seconds) as idle_seconds,
               SUM(duration_seconds) as total_seconds
        FROM activity_sessions
        WHERE date IN ({placeholders})
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()

    work_video_rows = conn.execute(f"""
        SELECT date,
               SUM(CASE WHEN category_key IN ('ai_tools','coding','reading','creative') THEN effective_seconds ELSE 0 END) as work_seconds,
               SUM(CASE WHEN category_key IN ('video','gaming') THEN effective_seconds ELSE 0 END) as video_seconds
        FROM activity_sessions
        WHERE date IN ({placeholders})
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()

    cat_rows = conn.execute(f"""
        SELECT category_key, category_name,
               SUM(effective_seconds) as effective_seconds,
               SUM(idle_seconds) as idle_seconds,
               SUM(duration_seconds) as total_seconds
        FROM activity_sessions
        WHERE date IN ({placeholders})
        GROUP BY category_key, category_name
        ORDER BY effective_seconds DESC
    """, dates).fetchall()

    app_rows = conn.execute(f"""
        SELECT process_name, category_key,
               SUM(effective_seconds) as effective_seconds,
               COUNT(*) as samples
        FROM activity_sessions
        WHERE date IN ({placeholders}) AND effective_seconds > 0
        GROUP BY process_name
        ORDER BY effective_seconds DESC
        LIMIT 20
    """, dates).fetchall()

    conn.close()

    daily_map = {r["date"]: dict(r) for r in daily_rows}
    wv_map = {r["date"]: dict(r) for r in work_video_rows}

    daily = []
    for d in dates:
        entry = daily_map.get(d, {"effective_seconds": 0, "idle_seconds": 0, "total_seconds": 0})
        wv = wv_map.get(d, {"work_seconds": 0, "video_seconds": 0})
        daily.append({
            "date": d,
            "effective_seconds": entry.get("effective_seconds", 0) or 0,
            "idle_seconds": entry.get("idle_seconds", 0) or 0,
            "total_seconds": entry.get("total_seconds", 0) or 0,
            "work_seconds": wv.get("work_seconds", 0) or 0,
            "video_seconds": wv.get("video_seconds", 0) or 0,
        })

    totals_effective = sum(d["effective_seconds"] for d in daily)
    totals_idle = sum(d["idle_seconds"] for d in daily)
    totals_work = sum(d["work_seconds"] for d in daily)
    totals_video = sum(d["video_seconds"] for d in daily)

    return {
        "dates": dates,
        "daily": daily,
        "by_category": [dict(r) for r in cat_rows],
        "by_app": [dict(r) for r in app_rows],
        "totals": {
            "effective_seconds": totals_effective,
            "idle_seconds": totals_idle,
            "total_seconds": totals_effective + totals_idle,
            "work_seconds": totals_work,
            "video_seconds": totals_video,
        },
    }


def _query_date_range_from_logs(db_path, dates):
    """Old per-sample range query (fallback for pre-v1.1 data)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    placeholders = ",".join("?" * len(dates))

    daily_rows = conn.execute(f"""
        SELECT date,
               SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
               SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
               SUM(duration_seconds) as total_seconds
        FROM activity_logs
        WHERE date IN ({placeholders})
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()

    work_video_rows = conn.execute(f"""
        SELECT date,
               SUM(CASE WHEN category_key IN ('ai_tools','coding','reading') AND is_effective
                   THEN duration_seconds ELSE 0 END) as work_seconds,
               SUM(CASE WHEN category_key = 'video' AND is_effective
                   THEN duration_seconds ELSE 0 END) as video_seconds
        FROM activity_logs
        WHERE date IN ({placeholders})
        GROUP BY date
        ORDER BY date
    """, dates).fetchall()

    cat_rows = conn.execute(f"""
        SELECT category_key, category_name,
               SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
               SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
               SUM(duration_seconds) as total_seconds
        FROM activity_logs
        WHERE date IN ({placeholders})
        GROUP BY category_key, category_name
        ORDER BY effective_seconds DESC
    """, dates).fetchall()

    app_rows = conn.execute(f"""
        SELECT process_name, category_key,
               SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
               COUNT(*) as samples
        FROM activity_logs
        WHERE date IN ({placeholders}) AND is_effective = 1
        GROUP BY process_name
        ORDER BY effective_seconds DESC
        LIMIT 20
    """, dates).fetchall()

    conn.close()

    daily_map = {r["date"]: dict(r) for r in daily_rows}
    wv_map = {r["date"]: dict(r) for r in work_video_rows}

    daily = []
    for d in dates:
        entry = daily_map.get(d, {"effective_seconds": 0, "idle_seconds": 0, "total_seconds": 0})
        wv = wv_map.get(d, {"work_seconds": 0, "video_seconds": 0})
        daily.append({
            "date": d,
            "effective_seconds": entry.get("effective_seconds", 0) or 0,
            "idle_seconds": entry.get("idle_seconds", 0) or 0,
            "total_seconds": entry.get("total_seconds", 0) or 0,
            "work_seconds": wv.get("work_seconds", 0) or 0,
            "video_seconds": wv.get("video_seconds", 0) or 0,
        })

    totals_effective = sum(d["effective_seconds"] for d in daily)
    totals_idle = sum(d["idle_seconds"] for d in daily)
    totals_work = sum(d["work_seconds"] for d in daily)
    totals_video = sum(d["video_seconds"] for d in daily)

    return {
        "dates": dates,
        "daily": daily,
        "by_category": [dict(r) for r in cat_rows],
        "by_app": [dict(r) for r in app_rows],
        "totals": {
            "effective_seconds": totals_effective,
            "idle_seconds": totals_idle,
            "total_seconds": totals_effective + totals_idle,
            "work_seconds": totals_work,
            "video_seconds": totals_video,
        },
    }
