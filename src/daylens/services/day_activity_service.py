"""Read-only, evidence-based full-day activity details.

Wall-clock spans locate evidence; persisted counters measure it. Unknown time
is never converted into idle time, and excluded evidence never joins events.
"""

from __future__ import annotations

import hashlib
import math
from datetime import datetime, timedelta

from .. import database
from ..repositories.stats_repository import session_row_is_anomalous
from ..timeline import allocate_integer_by_weights
from ..utils import parse_nonnegative_int


_COUNTERS = ("duration_seconds", "effective_seconds", "engaged_seconds",
             "passive_seconds", "idle_seconds")
_IDENTITY = ("process_name", "category_key",
             "metric_version", "classification_version")


def _day_bounds(day: str) -> tuple[datetime, datetime]:
    start = datetime.strptime(day, "%Y-%m-%d")
    if start.date().isoformat() != day:
        raise ValueError("日期须为 YYYY-MM-DD")
    return start, start + timedelta(days=1)


def _local_naive(value: datetime, captured: datetime) -> datetime:
    if value.utcoffset() is not None:
        value = value.astimezone(captured.tzinfo) if captured.tzinfo else value.astimezone()
    return value.replace(tzinfo=None)


def _segment(kind: str, start: float, end: float, event_id=None) -> dict:
    return {"kind": kind, "start_second": start, "end_second": end,
            "event_id": event_id}


def _empty_model(day: str, captured: datetime) -> dict:
    return {"day": day, "status": "empty", "captured_at": captured.isoformat(),
            "last_recorded_at": None, "warnings": [], "events": [],
            "segments": [], "totals": {key: 0 for key in _COUNTERS[1:]}}


def _warn(model: dict, message: str) -> None:
    if message not in model["warnings"]:
        model["warnings"].append(message)


def _idle(row: dict) -> bool:
    return str(row.get("category_key") or "") == "idle" or str(row.get("category_name") or "") == "空闲"


def _title(row: dict) -> str:
    normalized = " ".join(str(row.get("normalized_title") or "").split())
    return normalized or " ".join(str(row.get("window_title") or "").split())


def _clipped_counters(row: dict, start: datetime, end: datetime,
                      left: datetime, right: datetime) -> dict:
    # Allocate nested counters against their parent's integer capacity. Using
    # the same cumulative prefixes on independently read dates preserves both
    # source totals and each clipped part's exact attention identities.
    weights = [(left - start).total_seconds(), (right - left).total_seconds(),
               (end - right).total_seconds()]
    duration = allocate_integer_by_weights(row["duration_seconds"], weights)
    effective = allocate_integer_by_weights(row["effective_seconds"], duration)
    if row["duration_seconds"] == row["effective_seconds"] + row["idle_seconds"]:
        idle = [total - active for total, active in zip(duration, effective)]
    else:
        # Inexact legacy compositions must not be silently repaired: retain
        # their raw counters; their events already expose the legacy warning.
        idle = allocate_integer_by_weights(row["idle_seconds"], weights)
    if row["effective_seconds"] == row["engaged_seconds"] + row["passive_seconds"]:
        engaged = allocate_integer_by_weights(row["engaged_seconds"], effective)
        passive = [total - active for total, active in zip(effective, engaged)]
    else:
        engaged = allocate_integer_by_weights(row["engaged_seconds"], weights)
        passive = allocate_integer_by_weights(row["passive_seconds"], weights)
    return {"duration_seconds": duration[1], "effective_seconds": effective[1],
            "engaged_seconds": engaged[1], "passive_seconds": passive[1],
            "idle_seconds": idle[1]}


def _event(record: dict) -> dict:
    row = record["row"]
    counters = record["counters"]
    legacy = str(row.get("metric_version") or "legacy") == "legacy"
    event = {"id": "", "start_time": record["left"].isoformat(),
             "end_time": record["right"].isoformat(),
             "start_second": record["start"], "end_second": record["end"],
             "app": str(row.get("process_name") or ""),
             "process_name": str(row.get("process_name") or ""),
             "title": _title(row),
             "category_key": str(row.get("category_key") or ""),
             "category_name": str(row.get("category_name") or ""),
             **counters, "legacy": legacy,
             "contains_idle": counters["idle_seconds"] > 0,
             "is_long": counters["effective_seconds"] >= 300,
             "source_session_ids": [record["session_id"]]}
    if legacy:
        event["engaged_seconds"] = event["passive_seconds"] = None
    return event


def _finish_event(event: dict, day: str, details: list[dict], resolve_display) -> None:
    identity = repr((day, event["source_session_ids"], event["start_time"], event["end_time"]))
    event["id"] = "activity-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    event["is_long"] = event["effective_seconds"] >= 300
    if resolve_display is not None:
        event["app"] = str(resolve_display(event["process_name"], details))


def build_day_activity(rows, day: str, *, captured_at: datetime | None = None,
                       sample_interval: float = 1, resolve_display=None) -> dict:
    """Build a detached presentation model without altering persisted rows."""
    captured = captured_at or datetime.now()
    model = _empty_model(day, captured)
    try:
        day_start, day_end = _day_bounds(day)
    except (TypeError, ValueError, OverflowError):
        model["status"] = "unavailable"
        _warn(model, "日期无效，无法读取活动详情。")
        model["segments"] = [_segment("missing", 0, 86400)]
        return model
    now = _local_naive(captured, captured)
    visible_end = min(day_end, max(day_start, now))
    limit = (visible_end - day_start).total_seconds()
    try:
        sampling_tolerance = max(0.0, float(sample_interval))
        if not math.isfinite(sampling_tolerance):
            sampling_tolerance = 1
    except (TypeError, ValueError, OverflowError):
        sampling_tolerance = 1
    seam = min(2.0, sampling_tolerance)

    records = []
    seen = {}
    unknown_barrier = False
    for index, raw in enumerate(rows):
        row = dict(raw)
        session_id = str(row.get("session_id") or row.get("id") or f"row-{index}")
        # A repeated logical session is compared by evidence, not SQLite's
        # physical row ID or automatic creation timestamp.
        fingerprint = {key: value for key, value in row.items() if key not in {"id", "created_at"}}
        duplicates = seen.setdefault(session_id, [])
        if any(previous["fingerprint"] == fingerprint for previous in duplicates):
            continue
        record = {"row": row, "session_id": session_id,
                  "fingerprint": fingerprint, "bad": False}
        if duplicates:
            record["bad"] = True
            for previous in duplicates:
                previous["bad"] = True
            _warn(model, "同一会话 ID 的记录相互冲突，相关区间未计入可信时长。")
        duplicates.append(record)
        try:
            start = _local_naive(datetime.fromisoformat(row["start_time"]), captured)
            end = _local_naive(datetime.fromisoformat(row["end_time"]), captured)
        except (KeyError, TypeError, ValueError, OverflowError):
            unknown_barrier = True
            _warn(model, "存在时间戳无效的记录，无法确定其活动区间。")
            continue
        if end <= start:
            unknown_barrier = True
            _warn(model, "存在无效或零长度的会话区间，未计入可信时长。")
            continue
        left, right = max(day_start, start), min(visible_end, end)
        if right <= left:
            continue
        record.update(left=left, right=right,
                      start=(left - day_start).total_seconds(),
                      end=(right - day_start).total_seconds())
        legacy = str(row.get("metric_version") or "legacy") == "legacy"
        validation_row = dict(row)
        if legacy:
            validation_row.setdefault("engaged_seconds", 0)
            validation_row.setdefault("passive_seconds", 0)
        anomalous = session_row_is_anomalous(validation_row)
        span = (end - start).total_seconds()
        if not anomalous:
            counters = {key: parse_nonnegative_int(validation_row[key]) for key in _COUNTERS}
            # The first sampled tick can contribute one interval before the
            # persisted second-resolution start/end span catches up. Preserve
            # that legitimate overhead; never scale the stored counters.
            maximum = span + sampling_tolerance
            anomalous = (any(value > maximum for value in counters.values())
                         or counters["effective_seconds"] + counters["idle_seconds"] > maximum
                         or counters["effective_seconds"] > counters["duration_seconds"]
                         or counters["idle_seconds"] > counters["duration_seconds"])
        if anomalous:
            record["bad"] = True
            _warn(model, "存在计时异常的记录，相关区间未计入可信时长。")
        else:
            record["counters"] = _clipped_counters(counters, start, end, left, right)
        records.append(record)

    records.sort(key=lambda record: (record["start"], record["end"], record["session_id"]))
    # Sweep connected overlap components. All members are excluded; resolving
    # only the first pair would leave a misleading tail in chained overlaps.
    component = []
    component_end = -1
    for record in records:
        if component and record["start"] >= component_end:
            if len(component) > 1:
                for member in component:
                    member["bad"] = True
                _warn(model, "存在相互重叠的会话，相关区间未计入可信时长。")
            component = []
            component_end = -1
        component.append(record)
        component_end = max(component_end, record["end"])
    if len(component) > 1:
        for member in component:
            member["bad"] = True
        _warn(model, "存在相互重叠的会话，相关区间未计入可信时长。")

    spans = []
    previous = None
    event = None
    details = []
    for record in records:
        if record["bad"]:
            spans.append(_segment("unreliable", record["start"], record["end"]))
            previous = None
            continue
        row = record["row"]
        identity = tuple(str(row.get(key) or ("legacy" if key.endswith("version") else ""))
                         for key in _IDENTITY) + (_title(row),)
        idle = _idle(row)
        can_join = (not unknown_barrier and previous is not None and not idle
                    and not _idle(previous["row"])
                    and identity == previous["identity"]
                    and 0 <= record["start"] - previous["end"] <= seam
                    and not record["counters"]["idle_seconds"]
                    and not previous["counters"]["idle_seconds"])
        if can_join:
            event["end_time"] = record["right"].isoformat()
            event["end_second"] = record["end"]
            for key in _COUNTERS:
                if event[key] is not None:
                    event[key] += record["counters"][key]
            event["contains_idle"] |= record["counters"]["idle_seconds"] > 0
            event["source_session_ids"].append(record["session_id"])
            details.append(row)
        else:
            event = _event(record)
            details = [row]
            model["events"].append(event)
            event["_details"] = details
        record["identity"] = identity
        previous = record

    for event in model["events"]:
        details = event.pop("_details")
        try:
            _finish_event(event, day, details, resolve_display)
        except Exception:
            _warn(model, "部分应用显示名称解析失败，已显示进程名。")
        if event["legacy"]:
            _warn(model, "包含旧版计时记录；有效时长保留，主动与被动时长不可确定。")
        kind = "idle" if _idle(event) else "activity"
        spans.append(_segment(kind, event["start_second"], event["end_second"], event["id"]))
        for key in _COUNTERS[1:]:
            if event[key] is None:
                model["totals"][key] = None
            elif model["totals"][key] is not None:
                model["totals"][key] += event[key]

    # Adjacent/overlapping unreliable spans become one explicit uncertainty
    # band. Normal spans cannot overlap after the component exclusion above.
    cursor = 0
    for span in sorted(spans, key=lambda value: (value["start_second"], value["end_second"])):
        if span["start_second"] > cursor:
            model["segments"].append(_segment("missing", cursor, span["start_second"]))
        if (model["segments"] and span["kind"] == "unreliable"
                and model["segments"][-1]["kind"] == "unreliable"
                and span["start_second"] <= cursor):
            model["segments"][-1]["end_second"] = max(cursor, span["end_second"])
        else:
            model["segments"].append(span)
        cursor = max(cursor, span["end_second"])
    if cursor < limit:
        model["segments"].append(_segment("missing", cursor, limit))
    if limit < 86400:
        model["segments"].append(_segment("future", limit, 86400))
    if records:
        model["last_recorded_at"] = max(record["right"] for record in records).isoformat()
    model["status"] = "partial" if model["warnings"] else ("ready" if model["events"] else "empty")
    return model


def load_day_activity(db_path, day: str, *, captured_at: datetime | None = None,
                      sample_interval: float = 1, resolve_display=None,
                      session_loader=None) -> dict:
    """Read exactly one interval query; failures cannot escape into recording."""
    captured = captured_at or datetime.now()
    loader = session_loader or database.query_sessions_overlapping
    try:
        start, end = _day_bounds(day)
        rows = loader(db_path, start.isoformat(sep=" "), end.isoformat(sep=" "))
        return build_day_activity(rows, day, captured_at=captured,
                                  sample_interval=sample_interval,
                                  resolve_display=resolve_display)
    except Exception:
        model = build_day_activity([], day, captured_at=captured)
        model["status"] = "unavailable"
        _warn(model, "活动详情暂时不可读取；未修改历史记录。")
        return model
