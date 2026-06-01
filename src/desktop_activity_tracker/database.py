"""SQLite database operations for activity logs and summaries."""

import os
import sqlite3
from datetime import datetime, timedelta

from . import get_app_root


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
"""


def get_db_path(config):
    db_path = config.get("db_path", "data/usage.db")
    if not os.path.isabs(db_path):
        db_path = os.path.join(get_app_root(), db_path)
    return db_path


def init_db(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


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


def query_date(db_path, date_str):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM activity_logs WHERE date = ? ORDER BY timestamp",
        (date_str,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def query_date_stats(db_path, date_str):
    """Return aggregated stats for a given date."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    # Overall totals
    totals = conn.execute("""
        SELECT
            COUNT(*) as total_samples,
            SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
            SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
            SUM(duration_seconds) as total_seconds
        FROM activity_logs WHERE date = ?
    """, (date_str,)).fetchone()

    # By category
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

    # By app
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

    # Top window titles per process
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
        "by_app": [dict(r) for r in by_app],
        "by_app_detail": [dict(r) for r in by_app_detail],
    }


def query_entertainment_trend(db_path, days=3):
    """Return entertainment effective seconds for the last N days."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row

    today = datetime.now().date()
    dates = [(today - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    dates.reverse()

    rows = conn.execute("""
        SELECT date,
               SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as entertainment_seconds
        FROM activity_logs
        WHERE date IN ({}) AND category_key = 'video'
        GROUP BY date
        ORDER BY date
    """.format(",".join("?" * len(dates))), dates).fetchall()

    conn.close()

    result_map = {r["date"]: r["entertainment_seconds"] or 0 for r in rows}
    return [{"date": d, "entertainment_seconds": result_map.get(d, 0)} for d in dates]
