"""Stats query implementations split from the legacy database module."""

from __future__ import annotations

import re
from bisect import bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation


WORK_CATEGORY_KEYS = frozenset(
    {"ai_tools", "coding", "office", "reading", "creative"}
)
# attention-v1 counters are incremented and rewritten as mutually exclusive
# buckets, so persisted integer identities are exact and use a fixed tolerance.
ATTENTION_V1_COMPOSITION_TOLERANCE_SECONDS = 0
DEFAULT_WALL_CLOCK_TOLERANCE_SECONDS = 300

_STRICT_DATETIME_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:[+-][0-9]{2}:[0-9]{2})?"
)


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


def _parse_strict_datetime(value) -> datetime | None:
    """Parse only DayLens' canonical second-resolution timestamp format."""
    if type(value) is not str or _STRICT_DATETIME_PATTERN.fullmatch(value) is None:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if parsed.isoformat(sep=" ", timespec="seconds") != value:
        return None
    return parsed


def _normalized_datetime(value: datetime) -> tuple[str, datetime]:
    if value.utcoffset() is None:
        return "naive", value
    return "aware", value.astimezone(timezone.utc)


def _strict_session_interval(
    start_value,
    end_value,
) -> tuple[str, datetime, datetime] | None:
    start_time = _parse_strict_datetime(start_value)
    end_time = _parse_strict_datetime(end_value)
    if start_time is None or end_time is None:
        return None
    start_semantics, normalized_start = _normalized_datetime(start_time)
    end_semantics, normalized_end = _normalized_datetime(end_time)
    if start_semantics != end_semantics or normalized_end < normalized_start:
        return None
    return start_semantics, normalized_start, normalized_end


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

    interval = _strict_session_interval(row["start_time"], row["end_time"])
    if interval is None:
        return True
    _, normalized_start, normalized_end = interval
    try:
        wall_seconds = (normalized_end - normalized_start).total_seconds()
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
        row_keys = set(row.keys()) if hasattr(row, "keys") else set()
        timestamp_valid = True
        if "timestamp" in row_keys:
            parsed_timestamp = _parse_strict_datetime(row["timestamp"])
            timestamp_valid = (
                parsed_timestamp is not None
                and parsed_timestamp.date().isoformat() == date_str
            )
        anomalous = not valid_duration or duration < 0 or not timestamp_valid
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


@dataclass(frozen=True)
class _MergedIntervals:
    starts: tuple[datetime, ...]
    ends: tuple[datetime, ...]

    def contains(self, moment: datetime) -> bool:
        index = bisect_right(self.starts, moment) - 1
        return index >= 0 and moment <= self.ends[index]


def _merge_intervals(
    intervals: list[tuple[datetime, datetime]],
) -> _MergedIntervals:
    if not intervals:
        return _MergedIntervals((), ())
    merged: list[list[datetime]] = []
    for start_time, end_time in sorted(intervals):
        if (
            merged
            and start_time <= merged[-1][1] + timedelta(seconds=1)
        ):
            if end_time > merged[-1][1]:
                merged[-1][1] = end_time
        else:
            merged.append([start_time, end_time])
    return _MergedIntervals(
        tuple(interval[0] for interval in merged),
        tuple(interval[1] for interval in merged),
    )


def _coverage_by_date(session_rows: list[dict]) -> dict[str, dict[str, _MergedIntervals]]:
    raw: dict[str, dict[str, list[tuple[datetime, datetime]]]] = {}
    for row in session_rows:
        interval = _strict_session_interval(
            row.get("start_time"),
            row.get("end_time"),
        )
        if interval is None:
            continue
        semantics, normalized_start, normalized_end = interval
        date_intervals = raw.setdefault(
            str(row.get("date", "") or ""),
            {"naive": [], "aware": []},
        )
        date_intervals[semantics].append(
            (normalized_start, normalized_end)
        )

    return {
        date_str: {
            semantics: _merge_intervals(intervals)
            for semantics, intervals in by_semantics.items()
        }
        for date_str, by_semantics in raw.items()
    }


def _filter_uncovered_legacy_rows(
    session_rows: list[dict],
    legacy_rows: list[dict],
) -> list[dict]:
    coverage = _coverage_by_date(session_rows)
    uncovered: list[dict] = []
    for row in legacy_rows:
        date_str = str(row.get("date", "") or "")
        timestamp = _parse_strict_datetime(row.get("timestamp"))
        if timestamp is None or timestamp.date().isoformat() != date_str:
            uncovered.append(row)
            continue
        semantics, normalized_timestamp = _normalized_datetime(timestamp)
        intervals = coverage.get(date_str, {}).get(semantics)
        if intervals is None or not intervals.contains(normalized_timestamp):
            uncovered.append(row)
    return uncovered


def _load_mixed_history_rows(
    read_conn,
    db_path: str,
    dates: list[str],
) -> tuple[list[dict], list[dict]]:
    placeholders = ",".join("?" * len(dates))
    with read_conn(db_path) as conn:
        session_rows = conn.execute(
            f"""
            SELECT session_id, start_time, end_time, date, process_name,
                   normalized_title, category_key, category_name,
                   duration_seconds, effective_seconds, engaged_seconds,
                   passive_seconds, idle_seconds, metric_version,
                   classification_version
            FROM activity_sessions
            WHERE date IN ({placeholders})
            ORDER BY date, id
            """,
            dates,
        ).fetchall()
        legacy_rows = conn.execute(
            f"""
            SELECT timestamp, date, process_name, window_title, category_key,
                   category_name, is_effective, idle_seconds, duration_seconds
            FROM activity_logs
            WHERE date IN ({placeholders})
            ORDER BY date, id
            """,
            dates,
        ).fetchall()
    sessions = [dict(row) for row in session_rows]
    legacy = [dict(row) for row in legacy_rows]
    return sessions, _filter_uncovered_legacy_rows(sessions, legacy)


def _empty_activity_day(date_str: str) -> dict:
    return {
        "date": date_str,
        "total_samples": 0,
        "effective_seconds": 0,
        "idle_seconds": 0,
        "total_seconds": 0,
        "work_seconds": 0,
        "video_seconds": 0,
        **_empty_trusted_summary(),
    }


def _aggregate_mixed_history(
    dates: list[str],
    session_rows: list[dict],
    legacy_rows: list[dict],
) -> dict:
    daily_map = {date_str: _empty_activity_day(date_str) for date_str in dates}
    category_map: dict[tuple[str, str], dict] = {}
    app_map: dict[tuple[str, str], dict] = {}
    app_detail_map: dict[tuple[str, str, str, str], dict] = {}

    def add_category(
        row: dict,
        *,
        effective: int,
        engaged: int,
        passive: int,
        idle: int,
        duration: int,
    ) -> None:
        key = (
            str(row.get("category_key", "") or ""),
            str(row.get("category_name", "") or ""),
        )
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
        for field, value in (
            ("effective_seconds", effective),
            ("engaged_seconds", engaged),
            ("passive_seconds", passive),
            ("idle_seconds", idle),
            ("total_seconds", duration),
        ):
            merged[field] += value

    def add_app(
        row: dict,
        *,
        title: str,
        effective: int,
        engaged: int,
        passive: int,
    ) -> None:
        process_name = str(row.get("process_name", "") or "")
        category_key = str(row.get("category_key", "") or "")
        category_name = str(row.get("category_name", "") or "")
        app_key = (process_name, category_key)
        app = app_map.setdefault(
            app_key,
            {
                "process_name": process_name,
                "window_title": title,
                "category_key": category_key,
                "category_name": category_name,
                "effective_seconds": 0,
                "engaged_seconds": 0,
                "passive_seconds": 0,
                "samples": 0,
            },
        )
        app["effective_seconds"] += effective
        app["engaged_seconds"] += engaged
        app["passive_seconds"] += passive
        app["samples"] += 1

        detail_key = (process_name, title, category_key, category_name)
        detail = app_detail_map.setdefault(
            detail_key,
            {
                "process_name": process_name,
                "window_title": title,
                "category_key": category_key,
                "category_name": category_name,
                "effective_seconds": 0,
                "engaged_seconds": 0,
                "passive_seconds": 0,
            },
        )
        detail["effective_seconds"] += effective
        detail["engaged_seconds"] += engaged
        detail["passive_seconds"] += passive

    def add_standard_totals(
        row: dict,
        *,
        effective: int,
        idle: int,
        duration: int,
    ) -> dict:
        date_str = str(row.get("date", "") or "")
        day = daily_map[date_str]
        day["total_samples"] += 1
        day["effective_seconds"] += effective
        day["idle_seconds"] += idle
        day["total_seconds"] += duration
        category_key = str(row.get("category_key", "") or "")
        if category_key in WORK_CATEGORY_KEYS:
            day["work_seconds"] += effective
        if category_key in {"video", "gaming"}:
            day["video_seconds"] += effective
        return day

    for row in session_rows:
        duration = _integer(row.get("duration_seconds"))
        effective = _integer(row.get("effective_seconds"))
        engaged = _integer(row.get("engaged_seconds"))
        passive = _integer(row.get("passive_seconds"))
        idle = _integer(row.get("idle_seconds"))
        add_standard_totals(
            row,
            effective=effective,
            idle=idle,
            duration=duration,
        )
        if str(row.get("category_name", "") or "") != "空闲":
            add_category(
                row,
                effective=effective,
                engaged=engaged,
                passive=passive,
                idle=idle,
                duration=duration,
            )
        if effective > 0:
            add_app(
                row,
                title=str(row.get("normalized_title", "") or ""),
                effective=effective,
                engaged=engaged,
                passive=passive,
            )

    for row in legacy_rows:
        duration = _integer(row.get("duration_seconds"))
        effective = (
            duration if _integer(row.get("is_effective")) != 0 else 0
        )
        idle = 0 if effective else duration
        add_standard_totals(
            row,
            effective=effective,
            idle=idle,
            duration=duration,
        )
        add_category(
            row,
            effective=effective,
            engaged=0,
            passive=0,
            idle=idle,
            duration=duration,
        )
        if effective > 0:
            add_app(
                row,
                title=str(row.get("window_title", "") or ""),
                effective=effective,
                engaged=0,
                passive=0,
            )

    session_trust, session_trust_by_date = _summarize_session_rows(
        session_rows
    )
    legacy_trust, legacy_trust_by_date = _summarize_legacy_log_rows(
        legacy_rows
    )
    for date_str, day in daily_map.items():
        day.update(
            _merge_trusted_summaries(
                [
                    session_trust_by_date.get(
                        date_str,
                        _empty_trusted_summary(),
                    ),
                    legacy_trust_by_date.get(
                        date_str,
                        _empty_trusted_summary(),
                    ),
                ]
            )
        )

    daily = [daily_map[date_str] for date_str in dates]
    totals = {
        "effective_seconds": sum(row["effective_seconds"] for row in daily),
        "idle_seconds": sum(row["idle_seconds"] for row in daily),
        "total_seconds": sum(row["total_seconds"] for row in daily),
        "work_seconds": sum(row["work_seconds"] for row in daily),
        "video_seconds": sum(row["video_seconds"] for row in daily),
        **_merge_trusted_summaries([session_trust, legacy_trust]),
    }
    return {
        "dates": dates,
        "daily": daily,
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
        "totals": totals,
    }


def query_date_stats(read_conn, db_path: str, date_str: str) -> dict:
    session_rows, legacy_rows = _load_mixed_history_rows(
        read_conn,
        db_path,
        [date_str],
    )
    payload = _aggregate_mixed_history(
        [date_str],
        session_rows,
        legacy_rows,
    )
    day = payload["daily"][0]
    totals = {
        "total_samples": day["total_samples"],
        "effective_seconds": day["effective_seconds"],
        "idle_seconds": day["idle_seconds"],
        "total_seconds": day["total_seconds"],
        **{
            field: day[field]
            for field in _empty_trusted_summary()
        },
    }
    return {
        "totals": totals,
        "by_category": payload["by_category"],
        "by_app": payload["by_app"],
        "by_app_detail": payload["by_app_detail"],
    }


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

    session_rows, legacy_rows = _load_mixed_history_rows(
        read_conn,
        db_path,
        dates,
    )
    result_map = {date_str: 0 for date_str in dates}
    for row in session_rows:
        if str(row.get("category_key", "") or "") == "video":
            result_map[row["date"]] += _integer(
                row.get("effective_seconds")
            )
    for row in legacy_rows:
        if (
            str(row.get("category_key", "") or "") == "video"
            and _integer(row.get("is_effective")) != 0
        ):
            result_map[row["date"]] += _integer(
                row.get("duration_seconds")
            )
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
    work_categories = sorted(WORK_CATEGORY_KEYS)
    placeholders = ",".join("?" for _ in work_categories)
    with read_conn(db_path) as conn:
        rows = conn.execute(
            "SELECT DISTINCT date FROM activity_sessions "
            "WHERE engaged_seconds > 0 "
            f"AND category_key IN ({placeholders}) "
            "ORDER BY date DESC",
            work_categories,
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
    session_rows, legacy_rows = (
        _load_mixed_history_rows(read_conn, db_path, dates)
        if dates
        else ([], [])
    )
    payload = _aggregate_mixed_history(dates, session_rows, legacy_rows)
    payload.pop("by_app_detail", None)
    payload["by_app"] = payload["by_app"][:20]
    return payload
