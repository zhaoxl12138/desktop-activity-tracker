"""Stats query implementations split from the legacy database module."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation


WORK_CATEGORY_KEYS = frozenset(
    {"ai_tools", "coding", "office", "reading", "creative"}
)
# attention-v1 counters are incremented and rewritten as mutually exclusive
# buckets, so persisted integer identities are exact and use a fixed tolerance.
ATTENTION_V1_COMPOSITION_TOLERANCE_SECONDS = 0
DEFAULT_WALL_CLOCK_TOLERANCE_SECONDS = 300

# A legacy sample at either session boundary represents the same observed tick
# and is excluded. Invalid session timestamps produce NULL from julianday(), so
# they cannot accidentally hide otherwise usable legacy history.
_UNCOVERED_LEGACY_LOG = """
NOT EXISTS (
    SELECT 1
    FROM activity_sessions AS covering_session
    WHERE covering_session.date = activity_logs.date
      AND julianday(covering_session.start_time) IS NOT NULL
      AND julianday(covering_session.end_time) IS NOT NULL
      AND julianday(activity_logs.timestamp) BETWEEN
          julianday(covering_session.start_time)
          AND julianday(covering_session.end_time)
)
"""


def _empty_trusted_summary() -> dict:
    return {
        "engaged_seconds": 0,
        "passive_seconds": 0,
        "work_engaged_seconds": 0,
        "session_count": 0,
        "legacy_session_count": 0,
        "legacy_log_sample_count": 0,
        "legacy_granularity_unknown": False,
        "session_anomaly_count": 0,
        "legacy_log_anomaly_count": 0,
        # Compatibility total: anomalous sessions plus anomalous legacy logs.
        "anomaly_count": 0,
        "dates_with_data": [],
        "metric_versions": [],
        "classification_versions": [],
    }


def _strict_integer(value) -> tuple[int, bool]:
    if value is None:
        return 0, False
    try:
        number = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return 0, False
    if not number.is_finite() or number != number.to_integral_value():
        return 0, False
    return int(number), True


def _integer(value) -> int:
    number, valid = _strict_integer(value)
    return number if valid else 0


def _session_row_is_anomalous(row) -> bool:
    parsed = [
        _strict_integer(row[field])
        for field in (
            "duration_seconds",
            "effective_seconds",
            "engaged_seconds",
            "passive_seconds",
            "idle_seconds",
        )
    ]
    if not all(valid for _, valid in parsed):
        return True
    duration, effective, engaged, passive, idle = (
        number for number, _ in parsed
    )
    if any(value < 0 for value in (duration, effective, engaged, passive, idle)):
        return True

    metric_version = str(row["metric_version"] or "legacy")
    if metric_version != "legacy":
        components = engaged + passive + idle
        if (
            abs(duration - components)
            > ATTENTION_V1_COMPOSITION_TOLERANCE_SECONDS
        ):
            return True
        if (
            abs(effective - (engaged + passive))
            > ATTENTION_V1_COMPOSITION_TOLERANCE_SECONDS
        ):
            return True

    try:
        start_time = datetime.fromisoformat(str(row["start_time"]))
        end_time = datetime.fromisoformat(str(row["end_time"]))
    except (TypeError, ValueError, OverflowError):
        return True
    try:
        wall_seconds = (end_time - start_time).total_seconds()
    except (TypeError, OverflowError):
        return True
    return (
        wall_seconds < 0
        or abs(wall_seconds - duration) > DEFAULT_WALL_CLOCK_TOLERANCE_SECONDS
    )


def _summarize_session_rows(rows) -> tuple[dict, dict[str, dict]]:
    totals = _empty_trusted_summary()
    by_date: dict[str, dict] = {}
    seen_session_ids: set[str] = set()

    for row in rows:
        date_str = str(row["date"] or "")
        daily = by_date.setdefault(date_str, _empty_trusted_summary())
        session_id = str(row["session_id"] or "")
        duplicate = session_id in seen_session_ids
        seen_session_ids.add(session_id)
        anomalous = duplicate or _session_row_is_anomalous(row)
        metric_version = str(row["metric_version"] or "legacy")
        classification_version = str(row["classification_version"] or "legacy")
        engaged = _integer(row["engaged_seconds"])
        passive = _integer(row["passive_seconds"])
        work_engaged = (
            engaged if str(row["category_key"] or "") in WORK_CATEGORY_KEYS else 0
        )

        for summary in (totals, daily):
            summary["engaged_seconds"] += engaged
            summary["passive_seconds"] += passive
            summary["work_engaged_seconds"] += work_engaged
            summary["session_count"] += 1
            summary["legacy_session_count"] += int(metric_version == "legacy")
            summary["session_anomaly_count"] += int(anomalous)
            summary["anomaly_count"] += int(anomalous)
            summary["dates_with_data"].append(date_str)
            summary["metric_versions"].append(metric_version)
            summary["classification_versions"].append(classification_version)

    for summary in [totals, *by_date.values()]:
        summary["dates_with_data"] = sorted(
            {date for date in summary["dates_with_data"] if date}
        )
        summary["metric_versions"] = sorted(set(summary["metric_versions"]))
        summary["classification_versions"] = sorted(
            set(summary["classification_versions"])
        )
    return totals, by_date


def _summarize_legacy_log_rows(rows) -> tuple[dict, dict[str, dict]]:
    totals = _empty_trusted_summary()
    by_date: dict[str, dict] = {}
    for row in rows:
        date_str = str(row["date"] or "")
        daily = by_date.setdefault(date_str, _empty_trusted_summary())
        duration, valid_duration = _strict_integer(row["duration_seconds"])
        anomalous = not valid_duration or duration < 0
        for summary in (totals, daily):
            summary["legacy_log_sample_count"] += 1
            summary["legacy_granularity_unknown"] = True
            summary["legacy_log_anomaly_count"] += int(anomalous)
            summary["anomaly_count"] += int(anomalous)
            summary["dates_with_data"].append(date_str)
            summary["metric_versions"].append("legacy")
            summary["classification_versions"].append("legacy")

    for summary in [totals, *by_date.values()]:
        summary["dates_with_data"] = sorted(
            {date for date in summary["dates_with_data"] if date}
        )
        summary["metric_versions"] = sorted(set(summary["metric_versions"]))
        summary["classification_versions"] = sorted(
            set(summary["classification_versions"])
        )
    return totals, by_date


def _merge_trusted_summaries(summaries: list[dict]) -> dict:
    totals = _empty_trusted_summary()
    for row in summaries:
        for field in (
            "engaged_seconds",
            "passive_seconds",
            "work_engaged_seconds",
            "session_count",
            "legacy_session_count",
            "legacy_log_sample_count",
            "session_anomaly_count",
            "legacy_log_anomaly_count",
            "anomaly_count",
        ):
            totals[field] += _integer(row.get(field, 0))
        totals["legacy_granularity_unknown"] = (
            totals["legacy_granularity_unknown"]
            or bool(row.get("legacy_granularity_unknown", False))
        )
        totals["dates_with_data"].extend(row.get("dates_with_data", []))
        totals["metric_versions"].extend(row.get("metric_versions", []))
        totals["classification_versions"].extend(
            row.get("classification_versions", [])
        )
    totals["dates_with_data"] = sorted(set(totals["dates_with_data"]))
    totals["metric_versions"] = sorted(set(totals["metric_versions"]))
    totals["classification_versions"] = sorted(
        set(totals["classification_versions"])
    )
    return totals


def summarize_daily_trusted_metrics(
    daily_rows: list[dict],
    dates: list[str],
) -> dict:
    """Merge trusted fields for a sub-window of an already loaded range."""
    selected_dates = set(dates)
    return _merge_trusted_summaries(
        [
            row
            for row in daily_rows
            if str(row.get("date", "") or "") in selected_dates
        ]
    )


def query_date_stats_from_logs(read_conn, db_path: str, date_str: str) -> dict:
    with read_conn(db_path) as conn:
        totals = conn.execute(
            f"""
            SELECT
                COUNT(*) as total_samples,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_logs
            WHERE date = ? AND {_UNCOVERED_LEGACY_LOG}
            """,
            (date_str,),
        ).fetchone()

        by_category = conn.execute(
            f"""
            SELECT
                category_key,
                category_name,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                SUM(CASE WHEN is_effective = 0 THEN duration_seconds ELSE 0 END) as idle_seconds,
                SUM(duration_seconds) as total_seconds
            FROM activity_logs
            WHERE date = ? AND {_UNCOVERED_LEGACY_LOG}
            GROUP BY category_key, category_name
            ORDER BY effective_seconds DESC
            """,
            (date_str,),
        ).fetchall()

        by_app = conn.execute(
            f"""
            SELECT
                process_name,
                window_title,
                category_key,
                category_name,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds,
                COUNT(*) as samples
            FROM activity_logs
            WHERE date = ? AND is_effective = 1
              AND {_UNCOVERED_LEGACY_LOG}
            GROUP BY process_name, category_key
            ORDER BY effective_seconds DESC
            """,
            (date_str,),
        ).fetchall()

        by_app_detail = conn.execute(
            f"""
            SELECT
                process_name,
                window_title,
                category_key,
                category_name,
                SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as effective_seconds
            FROM activity_logs
            WHERE date = ? AND is_effective = 1
              AND {_UNCOVERED_LEGACY_LOG}
            GROUP BY process_name, window_title, category_key, category_name
            ORDER BY effective_seconds DESC
            LIMIT 50
            """,
            (date_str,),
        ).fetchall()

        trust_rows = conn.execute(
            f"""
            SELECT date, duration_seconds
            FROM activity_logs
            WHERE date = ? AND {_UNCOVERED_LEGACY_LOG}
            ORDER BY id
            """,
            (date_str,),
        ).fetchall()

    trusted_totals, _ = _summarize_legacy_log_rows(trust_rows)
    totals_payload = dict(totals)
    totals_payload.update(trusted_totals)

    return {
        "totals": totals_payload,
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
                SUM(engaged_seconds) as engaged_seconds,
                SUM(passive_seconds) as passive_seconds,
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
                SUM(engaged_seconds) as engaged_seconds,
                SUM(passive_seconds) as passive_seconds,
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
                SUM(effective_seconds) as effective_seconds,
                SUM(engaged_seconds) as engaged_seconds,
                SUM(passive_seconds) as passive_seconds
            FROM activity_sessions WHERE date = ? AND effective_seconds > 0
            GROUP BY process_name, normalized_title, category_key, category_name
            ORDER BY effective_seconds DESC
            LIMIT 50
            """,
            (date_str,),
        ).fetchall()

        trust_rows = conn.execute(
            """
            SELECT session_id, start_time, end_time, date, category_key,
                   duration_seconds, effective_seconds, engaged_seconds,
                   passive_seconds, idle_seconds, metric_version,
                   classification_version
            FROM activity_sessions
            WHERE date = ?
            ORDER BY id
            """,
            (date_str,),
        ).fetchall()

    trusted_totals, _ = _summarize_session_rows(trust_rows)
    totals_payload = dict(totals)
    totals_payload.update(trusted_totals)

    return {
        "totals": totals_payload,
        "by_category": [dict(row) for row in by_category],
        "by_app": [dict(row) for row in by_app],
        "by_app_detail": [dict(row) for row in by_app_detail],
    }


def query_date_stats(read_conn, db_path: str, date_str: str) -> dict:
    return _merge_daily_stats_payloads(
        [
            query_date_stats_from_sessions(read_conn, db_path, date_str),
            query_date_stats_from_logs(read_conn, db_path, date_str),
        ]
    )


def _merge_daily_stats_payloads(payloads: list[dict]) -> dict:
    totals = {
        "total_samples": 0,
        "effective_seconds": 0,
        "idle_seconds": 0,
        "total_seconds": 0,
    }
    category_map: dict[tuple[str, str], dict] = {}
    app_map: dict[tuple[str, str], dict] = {}
    app_detail_map: dict[tuple[str, str, str, str], dict] = {}

    for payload in payloads:
        payload_totals = payload.get("totals", {})
        for field in totals:
            totals[field] += payload_totals.get(field, 0) or 0

        for row in payload.get("by_category", []):
            key = (row.get("category_key", ""), row.get("category_name", ""))
            merged = category_map.setdefault(
                key,
                {
                    "category_key": key[0],
                    "category_name": key[1],
                    "effective_seconds": 0,
                    "engaged_seconds": 0,
                    "passive_seconds": 0,
                    "idle_seconds": 0,
                    "total_seconds": 0,
                },
            )
            for field in (
                "effective_seconds",
                "engaged_seconds",
                "passive_seconds",
                "idle_seconds",
                "total_seconds",
            ):
                merged[field] += row.get(field, 0) or 0

        for row in payload.get("by_app", []):
            key = (row.get("process_name", ""), row.get("category_key", ""))
            merged = app_map.setdefault(
                key,
                {
                    "process_name": key[0],
                    "window_title": row.get("window_title", ""),
                    "category_key": key[1],
                    "category_name": row.get("category_name", ""),
                    "effective_seconds": 0,
                    "engaged_seconds": 0,
                    "passive_seconds": 0,
                    "samples": 0,
                },
            )
            for field in (
                "effective_seconds",
                "engaged_seconds",
                "passive_seconds",
                "samples",
            ):
                merged[field] += row.get(field, 0) or 0

        for row in payload.get("by_app_detail", []):
            key = (
                row.get("process_name", ""),
                row.get("window_title", ""),
                row.get("category_key", ""),
                row.get("category_name", ""),
            )
            merged = app_detail_map.setdefault(
                key,
                {
                    "process_name": key[0],
                    "window_title": key[1],
                    "category_key": key[2],
                    "category_name": key[3],
                    "effective_seconds": 0,
                    "engaged_seconds": 0,
                    "passive_seconds": 0,
                },
            )
            for field in (
                "effective_seconds",
                "engaged_seconds",
                "passive_seconds",
            ):
                merged[field] += row.get(field, 0) or 0

    totals.update(
        _merge_trusted_summaries(
            [payload.get("totals", {}) for payload in payloads]
        )
    )
    return {
        "totals": totals,
        "by_category": sorted(
            category_map.values(),
            key=lambda row: row["effective_seconds"],
            reverse=True,
        ),
        "by_app": sorted(
            app_map.values(),
            key=lambda row: row["effective_seconds"],
            reverse=True,
        ),
        "by_app_detail": sorted(
            app_detail_map.values(),
            key=lambda row: row["effective_seconds"],
            reverse=True,
        )[:50],
    }


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
                   SUM(engaged_seconds) as engaged_seconds,
                   SUM(passive_seconds) as passive_seconds,
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
                   SUM(engaged_seconds) as engaged_seconds,
                   SUM(passive_seconds) as passive_seconds,
                   COUNT(*) as samples
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND effective_seconds > 0
            GROUP BY process_name, category_key
            ORDER BY effective_seconds DESC
            LIMIT 20
            """,
            dates,
        ).fetchall()

        trust_rows = conn.execute(
            f"""
            SELECT session_id, start_time, end_time, date, category_key,
                   duration_seconds, effective_seconds, engaged_seconds,
                   passive_seconds, idle_seconds, metric_version,
                   classification_version
            FROM activity_sessions
            WHERE date IN ({placeholders})
            ORDER BY id
            """,
            dates,
        ).fetchall()

    trusted_totals, trusted_by_date = _summarize_session_rows(trust_rows)
    return _build_range_payload(
        dates,
        daily_rows,
        work_video_rows,
        category_rows,
        app_rows,
        trusted_by_date,
        trusted_totals,
    )


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
              AND {_UNCOVERED_LEGACY_LOG}
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
              AND {_UNCOVERED_LEGACY_LOG}
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
              AND {_UNCOVERED_LEGACY_LOG}
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
              AND {_UNCOVERED_LEGACY_LOG}
            GROUP BY process_name, category_key
            ORDER BY effective_seconds DESC
            LIMIT 20
            """,
            dates,
        ).fetchall()

        trust_rows = conn.execute(
            f"""
            SELECT date, duration_seconds
            FROM activity_logs
            WHERE date IN ({placeholders})
              AND {_UNCOVERED_LEGACY_LOG}
            ORDER BY id
            """,
            dates,
        ).fetchall()

    trusted_totals, trusted_by_date = _summarize_legacy_log_rows(trust_rows)
    return _build_range_payload(
        dates,
        daily_rows,
        work_video_rows,
        category_rows,
        app_rows,
        trusted_by_date,
        trusted_totals,
    )


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
        session_rows = conn.execute(
            f"""
            SELECT date, SUM(effective_seconds) as entertainment_seconds
            FROM activity_sessions
            WHERE date IN ({placeholders}) AND category_key = 'video'
            GROUP BY date
            """,
            dates,
        ).fetchall()
        legacy_rows = conn.execute(
            f"""
            SELECT date,
                   SUM(CASE WHEN is_effective THEN duration_seconds ELSE 0 END) as entertainment_seconds
            FROM activity_logs
            WHERE date IN ({placeholders}) AND category_key = 'video'
              AND {_UNCOVERED_LEGACY_LOG}
            GROUP BY date
            ORDER BY date
            """,
            dates,
        ).fetchall()

    result_map = {date_str: 0 for date_str in dates}
    for row in [*session_rows, *legacy_rows]:
        result_map[row["date"]] += row["entertainment_seconds"] or 0
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


def query_sessions_for_dates(
    read_conn,
    db_path: str,
    dates: list[str],
) -> list[dict]:
    """Read complete session evidence for a date range in one query."""
    unique_dates = list(dict.fromkeys(dates))
    if not unique_dates:
        return []
    placeholders = ",".join("?" * len(unique_dates))
    with read_conn(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT session_id, start_time, end_time, date, process_name,
                   normalized_title, category_key, category_name,
                   duration_seconds, effective_seconds, engaged_seconds,
                   passive_seconds, idle_seconds, metric_version,
                   classification_version
            FROM activity_sessions
            WHERE date IN ({placeholders})
            ORDER BY start_time, id
            """,
            unique_dates,
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
                   duration_seconds, effective_seconds, engaged_seconds,
                   passive_seconds, idle_seconds
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
    dates = list(dict.fromkeys(dates))
    if not dates:
        return _merge_range_payloads([], [])

    return _merge_range_payloads(
        dates,
        [
            query_date_range_from_sessions(read_conn, db_path, dates),
            query_date_range_from_logs(read_conn, db_path, dates),
        ],
    )


def _merge_range_payloads(dates: list[str], payloads: list[dict]) -> dict:
    daily_map = {}
    category_map = {}
    app_map = {}

    for payload in payloads:
        for row in payload.get("daily", []):
            date_str = row["date"]
            merged = daily_map.setdefault(
                date_str,
                {
                    "date": date_str,
                    "effective_seconds": 0,
                    "idle_seconds": 0,
                    "total_seconds": 0,
                    "work_seconds": 0,
                    "video_seconds": 0,
                    **_empty_trusted_summary(),
                },
            )
            for field in (
                "effective_seconds",
                "idle_seconds",
                "total_seconds",
                "work_seconds",
                "video_seconds",
            ):
                merged[field] += row.get(field, 0) or 0
            trusted = _merge_trusted_summaries([merged, row])
            merged.update(trusted)

        for row in payload.get("by_category", []):
            key = (row.get("category_key", ""), row.get("category_name", ""))
            merged = category_map.setdefault(
                key,
                {
                    "category_key": key[0],
                    "category_name": key[1],
                    "effective_seconds": 0,
                    "engaged_seconds": 0,
                    "passive_seconds": 0,
                    "idle_seconds": 0,
                    "total_seconds": 0,
                },
            )
            for field in (
                "effective_seconds",
                "engaged_seconds",
                "passive_seconds",
                "idle_seconds",
                "total_seconds",
            ):
                merged[field] += row.get(field, 0) or 0

        for row in payload.get("by_app", []):
            key = (row.get("process_name", ""), row.get("category_key", ""))
            merged = app_map.setdefault(
                key,
                {
                    "process_name": key[0],
                    "category_key": key[1],
                    "effective_seconds": 0,
                    "engaged_seconds": 0,
                    "passive_seconds": 0,
                    "samples": 0,
                },
            )
            merged["effective_seconds"] += row.get("effective_seconds", 0) or 0
            merged["engaged_seconds"] += row.get("engaged_seconds", 0) or 0
            merged["passive_seconds"] += row.get("passive_seconds", 0) or 0
            merged["samples"] += row.get("samples", 0) or 0

    daily = [
        daily_map.get(
            date_str,
            {
                "date": date_str,
                "effective_seconds": 0,
                "engaged_seconds": 0,
                "passive_seconds": 0,
                "idle_seconds": 0,
                "total_seconds": 0,
                "work_seconds": 0,
                "video_seconds": 0,
                "work_engaged_seconds": 0,
                "session_count": 0,
                "legacy_session_count": 0,
                "legacy_log_sample_count": 0,
                "legacy_granularity_unknown": False,
                "session_anomaly_count": 0,
                "legacy_log_anomaly_count": 0,
                "anomaly_count": 0,
                "dates_with_data": [],
                "metric_versions": [],
                "classification_versions": [],
            },
        )
        for date_str in dates
    ]
    totals_effective = sum(row.get("effective_seconds", 0) or 0 for row in daily)
    totals_idle = sum(row.get("idle_seconds", 0) or 0 for row in daily)
    totals_work = sum(row.get("work_seconds", 0) or 0 for row in daily)
    totals_video = sum(row.get("video_seconds", 0) or 0 for row in daily)
    totals_duration = sum(row.get("total_seconds", 0) or 0 for row in daily)
    trusted_totals = _merge_trusted_summaries(
        [payload.get("totals", {}) for payload in payloads]
    )

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
            "total_seconds": totals_duration,
            "work_seconds": totals_work,
            "video_seconds": totals_video,
            **trusted_totals,
        },
    }


def _build_range_payload(
    dates: list[str],
    daily_rows,
    work_video_rows,
    category_rows,
    app_rows,
    trusted_by_date: dict[str, dict],
    trusted_totals: dict,
) -> dict:
    daily_map = {row["date"]: dict(row) for row in daily_rows}
    work_video_map = {row["date"]: dict(row) for row in work_video_rows}

    daily = []
    for date_str in dates:
        entry = daily_map.get(date_str, {"effective_seconds": 0, "idle_seconds": 0, "total_seconds": 0})
        work_video = work_video_map.get(date_str, {"work_seconds": 0, "video_seconds": 0})
        trusted = trusted_by_date.get(date_str, _empty_trusted_summary())
        daily.append(
            {
                "date": date_str,
                "effective_seconds": entry.get("effective_seconds", 0) or 0,
                "idle_seconds": entry.get("idle_seconds", 0) or 0,
                "total_seconds": entry.get("total_seconds", 0) or 0,
                "work_seconds": work_video.get("work_seconds", 0) or 0,
                "video_seconds": work_video.get("video_seconds", 0) or 0,
                **trusted,
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
            **trusted_totals,
        },
    }
