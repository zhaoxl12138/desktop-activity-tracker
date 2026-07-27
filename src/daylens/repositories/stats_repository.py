"""Stats query implementations split from the legacy database module."""

from __future__ import annotations

from datetime import datetime, timedelta


def query_date_stats_from_logs(read_conn, db_path: str, date_str: str) -> dict:
    with read_conn(db_path) as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) as total_samples,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_logs WHERE date = ?
            """,
            (date_str,),
        ).fetchone()

        by_category = conn.execute(
            """
            SELECT
                category_key,
                category_name,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_logs WHERE date = ?
            GROUP BY category_key, category_name
            ORDER BY effective_seconds DESC
            """,
            (date_str,),
        ).fetchall()

        by_app = conn.execute(
            """
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
            """,
            (date_str,),
        ).fetchall()

        by_app_detail = conn.execute(
            """
            SELECT
                process_name,
                window_title,
                category_key,
                category_name,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds
            FROM activity_logs WHERE date = ? AND is_effective = 1
            GROUP BY process_name, window_title, category_key, category_name
            ORDER BY effective_seconds DESC
            LIMIT 50
            """,
            (date_str,),
        ).fetchall()

    return {
        "totals": dict(totals),
        "by_category": [dict(row) for row in by_category],
        "by_app": [dict(row) for row in by_app],
        "by_app_detail": [dict(row) for row in by_app_detail],
    }


def query_date_stats_from_sessions(read_conn, db_path: str, date_str: str) -> dict:
    with read_conn(db_path) as conn:
        totals = conn.execute(
            """
            SELECT
                COUNT(*) as total_samples,
                SUM(effective_seconds) as effective_seconds,
                SUM(idle_seconds) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_sessions WHERE date = ?
            """,
            (date_str,),
        ).fetchone()

        by_category = conn.execute(
            """
            SELECT
                category_key,
                category_name,
                SUM(effective_seconds) as effective_seconds,
                SUM(idle_seconds) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_sessions WHERE date = ? AND category_name != '空闲'
            GROUP BY category_key, category_name
            ORDER BY effective_seconds DESC
            """,
            (date_str,),
        ).fetchall()

        by_app = conn.execute(
            """
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
            """,
            (date_str,),
        ).fetchall()

        by_app_detail = conn.execute(
            """
            SELECT
                process_name,
                normalized_title as window_title,
                category_key,
                category_name,
                SUM(effective_seconds) as effective_seconds
            FROM activity_sessions WHERE date = ? AND effective_seconds > 0
            GROUP BY process_name, normalized_title, category_key, category_name
            ORDER BY effective_seconds DESC
            LIMIT 50
            """,
            (date_str,),
        ).fetchall()

    return {
        "totals": dict(totals),
        "by_category": [dict(row) for row in by_category],
        "by_app": [dict(row) for row in by_app],
        "by_app_detail": [dict(row) for row in by_app_detail],
    }


def query_date_stats(read_conn, db_path: str, date_str: str) -> dict:
    with read_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM activity_sessions WHERE date = ?",
            (date_str,),
        ).fetchone()

    if row and row["cnt"] > 0:
        return query_date_stats_from_sessions(read_conn, db_path, date_str)
    return query_date_stats_from_logs(read_conn, db_path, date_str)


def query_date_range_from_sessions(read_conn, db_path: str, dates: list[str]) -> dict:
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))

        daily_rows = conn.execute(
            f"""
            SELECT date,
                   SUM(effective_seconds) as effective_seconds,
                   SUM(idle_seconds) as idle_seconds,
                   SUM(duration_seconds) as total_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

        work_video_rows = conn.execute(
            f"""
            SELECT date,
                   SUM(CASE WHEN category_key IN ('ai_tools','coding','office','reading','creative') THEN effective_seconds ELSE 0 END) as work_seconds,
                   SUM(CASE WHEN category_key IN ('video','gaming') THEN effective_seconds ELSE 0 END) as video_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders})
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

        category_rows = conn.execute(
            f"""
            SELECT category_key, category_name,
                   SUM(effective_seconds) as effective_seconds,
                   SUM(idle_seconds) as idle_seconds,
                   SUM(duration_seconds) as total_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND category_name != '空闲'
            GROUP BY category_key, category_name
            ORDER BY effective_seconds DESC
            """,
            dates,
        ).fetchall()

        app_rows = conn.execute(
            f"""
            SELECT process_name, category_key,
                   SUM(effective_seconds) as effective_seconds,
                   COUNT(*) as samples
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND effective_seconds > 0
            GROUP BY process_name, category_key
            ORDER BY effective_seconds DESC
            LIMIT 20
            """,
            dates,
        ).fetchall()

    return _build_range_payload(dates, daily_rows, work_video_rows, category_rows, app_rows)


def query_date_range_from_logs(read_conn, db_path: str, dates: list[str]) -> dict:
    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))

        daily_rows = conn.execute(
            f"""
            SELECT date,
                   SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                   SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                   SUM(duration_seconds) as total_seconds
            FROM activity_logs
            WHERE date IN ({placeholders})
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

        work_video_rows = conn.execute(
            f"""
            SELECT date,
                   SUM(CASE WHEN category_key IN ('ai_tools','coding','office','reading','creative') AND is_effective
                       THEN duration_seconds ELSE 0 END) as work_seconds,
                   SUM(CASE WHEN category_key IN ('video','gaming') AND is_effective
                       THEN duration_seconds ELSE 0 END) as video_seconds
            FROM activity_logs
            WHERE date IN ({placeholders})
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

        category_rows = conn.execute(
            f"""
            SELECT category_key, category_name,
                   SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                   SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                   SUM(duration_seconds) as total_seconds
            FROM activity_logs
            WHERE date IN ({placeholders})
            GROUP BY category_key, category_name
            ORDER BY effective_seconds DESC
            """,
            dates,
        ).fetchall()

        app_rows = conn.execute(
            f"""
            SELECT process_name, category_key,
                   SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                   COUNT(*) as samples
            FROM activity_logs
            WHERE date IN ({placeholders}) AND is_effective = 1
            GROUP BY process_name, category_key
            ORDER BY effective_seconds DESC
            LIMIT 20
            """,
            dates,
        ).fetchall()

    return _build_range_payload(dates, daily_rows, work_video_rows, category_rows, app_rows)


def query_date(read_conn, db_path: str, date_str: str) -> list[dict]:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM activity_logs WHERE date = ? ORDER BY timestamp",
            (date_str,),
        ).fetchall()
    return [dict(row) for row in rows]


def query_session_entertainment_trend(read_conn, db_path: str, days: int = 3) -> list[dict]:
    today = datetime.now().date()
    dates = [(today - timedelta(days=index)).strftime("%Y-%m-%d") for index in range(days)]
    dates.reverse()

    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"""
            SELECT date,
                   SUM(effective_seconds) as entertainment_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND category_key = 'video'
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

    result_map = {row["date"]: row["entertainment_seconds"] or 0 for row in rows}
    return [{"date": date_str, "entertainment_seconds": result_map.get(date_str, 0)} for date_str in dates]


def query_entertainment_trend(read_conn, db_path: str, days: int = 3) -> list[dict]:
    today = datetime.now().date()
    dates = [(today - timedelta(days=index)).strftime("%Y-%m-%d") for index in range(days)]
    dates.reverse()

    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        session_date_rows = conn.execute(
            f"SELECT DISTINCT date FROM activity_sessions WHERE date IN ({placeholders})",
            dates,
        ).fetchall()
        session_rows = conn.execute(
            f"""
            SELECT date, SUM(effective_seconds) as entertainment_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND category_key = 'video'
            GROUP BY date
            """,
            dates,
        ).fetchall()

        session_dates = {row["date"] for row in session_date_rows}
        legacy_dates = [date_str for date_str in dates if date_str not in session_dates]
        legacy_rows = []
        if legacy_dates:
            legacy_placeholders = ",".join("?" * len(legacy_dates))
            legacy_rows = conn.execute(
                f"""
                SELECT date,
                       SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as entertainment_seconds
                FROM activity_logs
                WHERE date IN ({legacy_placeholders}) AND category_key = 'video'
                GROUP BY date
                ORDER BY date
                """,
                legacy_dates,
            ).fetchall()

    result_map = {
        row["date"]: row["entertainment_seconds"] or 0
        for row in [*session_rows, *legacy_rows]
    }
    return [{"date": date_str, "entertainment_seconds": result_map.get(date_str, 0)} for date_str in dates]


def query_session_count(read_conn, db_path: str, date_str: str) -> int:
    with read_conn(db_path) as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM activity_sessions WHERE date = ?",
            (date_str,),
        ).fetchone()
    return row[0] if row else 0


def query_today_sessions(read_conn, db_path: str, date_str: str) -> list[dict]:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT session_id, start_time, end_time, process_name,
                   normalized_title, category_key, category_name,
                   duration_seconds, effective_seconds, idle_seconds
            FROM activity_sessions
            WHERE date = ?
            ORDER BY start_time
            """,
            (date_str,),
        ).fetchall()
    return [dict(row) for row in rows]


def query_category_detail(read_conn, db_path: str, date_str: str, category_key: str, limit: int = 5) -> list[dict]:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT process_name, normalized_title as window_title,
                   SUM(effective_seconds) as effective_seconds
            FROM activity_sessions
            WHERE date = ? AND category_key = ? AND effective_seconds > 0
            GROUP BY process_name, normalized_title
            ORDER BY effective_seconds DESC
            LIMIT ?
            """,
            (date_str, category_key, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def query_top_titles_by_category(read_conn, db_path: str, date_str: str, limit: int = 3) -> dict[str, list[str]]:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT category_key, normalized_title, SUM(effective_seconds) as total_sec
            FROM activity_sessions
            WHERE date = ? AND effective_seconds > 0 AND normalized_title != ''
            GROUP BY category_key, normalized_title
            ORDER BY category_key, total_sec DESC
            """,
            (date_str,),
        ).fetchall()

    result: dict[str, list[str]] = {}
    for row in rows:
        category_key = row["category_key"]
        title = row["normalized_title"]
        if category_key not in result:
            result[category_key] = []
        if len(result[category_key]) < limit:
            short_title = title[:28] + "…" if len(title) > 28 else title
            result[category_key].append(short_title)
    return result


def query_timeline_sessions(read_conn, db_path: str, date_str: str) -> list[dict]:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT session_id, start_time, end_time, process_name,
                   window_title, normalized_title, category_key, category_name,
                   duration_seconds, effective_seconds, idle_seconds
            FROM activity_sessions
            WHERE date = ?
            ORDER BY start_time
            """,
            (date_str,),
        ).fetchall()
    return [dict(row) for row in rows]


def count_consecutive_days(read_conn, db_path: str) -> int:
    with read_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM activity_sessions ORDER BY date DESC"
        ).fetchall()

    if not rows:
        return 0

    dates = [row["date"] for row in rows]
    today = datetime.now().strftime("%Y-%m-%d")
    if dates[0] != today:
        return 0

    count = 1
    for index in range(1, len(dates)):
        date1 = datetime.strptime(dates[index - 1], "%Y-%m-%d")
        date2 = datetime.strptime(dates[index], "%Y-%m-%d")
        if (date1 - date2).days == 1:
            count += 1
        else:
            break
    return count


def query_date_range_stats(read_conn, db_path: str, dates: list[str]) -> dict:
    if not dates:
        return {"dates": [], "daily": [], "by_category": [], "by_app": [], "totals": {}}

    with read_conn(db_path) as conn:
        placeholders = ",".join("?" * len(dates))
        rows = conn.execute(
            f"SELECT DISTINCT date FROM activity_sessions WHERE date IN ({placeholders})",
            dates,
        ).fetchall()

    session_date_set = {row["date"] for row in rows}
    session_dates = [date_str for date_str in dates if date_str in session_date_set]
    legacy_dates = [date_str for date_str in dates if date_str not in session_date_set]
    payloads = []
    if session_dates:
        payloads.append(query_date_range_from_sessions(read_conn, db_path, session_dates))
    if legacy_dates:
        payloads.append(query_date_range_from_logs(read_conn, db_path, legacy_dates))
    return _merge_range_payloads(dates, payloads)


def _merge_range_payloads(dates: list[str], payloads: list[dict]) -> dict:
    daily_map = {}
    category_map = {}
    app_map = {}

    for payload in payloads:
        for row in payload.get("daily", []):
            daily_map[row["date"]] = dict(row)

        for row in payload.get("by_category", []):
            key = (row.get("category_key", ""), row.get("category_name", ""))
            merged = category_map.setdefault(
                key,
                {
                    "category_key": key[0],
                    "category_name": key[1],
                    "effective_seconds": 0,
                    "idle_seconds": 0,
                    "total_seconds": 0,
                },
            )
            for field in ("effective_seconds", "idle_seconds", "total_seconds"):
                merged[field] += row.get(field, 0) or 0

        for row in payload.get("by_app", []):
            key = (row.get("process_name", ""), row.get("category_key", ""))
            merged = app_map.setdefault(
                key,
                {
                    "process_name": key[0],
                    "category_key": key[1],
                    "effective_seconds": 0,
                    "samples": 0,
                },
            )
            merged["effective_seconds"] += row.get("effective_seconds", 0) or 0
            merged["samples"] += row.get("samples", 0) or 0

    daily = [
        daily_map.get(
            date_str,
            {
                "date": date_str,
                "effective_seconds": 0,
                "idle_seconds": 0,
                "total_seconds": 0,
                "work_seconds": 0,
                "video_seconds": 0,
            },
        )
        for date_str in dates
    ]
    totals_effective = sum(row.get("effective_seconds", 0) or 0 for row in daily)
    totals_idle = sum(row.get("idle_seconds", 0) or 0 for row in daily)
    totals_work = sum(row.get("work_seconds", 0) or 0 for row in daily)
    totals_video = sum(row.get("video_seconds", 0) or 0 for row in daily)

    return {
        "dates": dates,
        "daily": daily,
        "by_category": sorted(
            category_map.values(), key=lambda row: row["effective_seconds"], reverse=True
        ),
        "by_app": sorted(
            app_map.values(), key=lambda row: row["effective_seconds"], reverse=True
        )[:20],
        "totals": {
            "effective_seconds": totals_effective,
            "idle_seconds": totals_idle,
            "total_seconds": totals_effective + totals_idle,
            "work_seconds": totals_work,
            "video_seconds": totals_video,
        },
    }


def _build_range_payload(dates: list[str], daily_rows, work_video_rows, category_rows, app_rows) -> dict:
    daily_map = {row["date"]: dict(row) for row in daily_rows}
    work_video_map = {row["date"]: dict(row) for row in work_video_rows}

    daily = []
    for date_str in dates:
        entry = daily_map.get(date_str, {"effective_seconds": 0, "idle_seconds": 0, "total_seconds": 0})
        work_video = work_video_map.get(date_str, {"work_seconds": 0, "video_seconds": 0})
        daily.append(
            {
                "date": date_str,
                "effective_seconds": entry.get("effective_seconds", 0) or 0,
                "idle_seconds": entry.get("idle_seconds", 0) or 0,
                "total_seconds": entry.get("total_seconds", 0) or 0,
                "work_seconds": work_video.get("work_seconds", 0) or 0,
                "video_seconds": work_video.get("video_seconds", 0) or 0,
            }
        )

    totals_effective = sum(item["effective_seconds"] for item in daily)
    totals_idle = sum(item["idle_seconds"] for item in daily)
    totals_work = sum(item["work_seconds"] for item in daily)
    totals_video = sum(item["video_seconds"] for item in daily)

    return {
        "dates": dates,
        "daily": daily,
        "by_category": [dict(row) for row in category_rows],
        "by_app": [dict(row) for row in app_rows],
        "totals": {
            "effective_seconds": totals_effective,
            "idle_seconds": totals_idle,
            "total_seconds": totals_effective + totals_idle,
            "work_seconds": totals_work,
            "video_seconds": totals_video,
        },
    }
