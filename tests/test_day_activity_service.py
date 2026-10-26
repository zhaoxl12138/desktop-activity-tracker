"""Day activity uses synthetic rows and temporary databases only."""

from __future__ import annotations

import importlib
import importlib.util
import random
import sqlite3
from copy import deepcopy
from datetime import datetime, timedelta

import pytest


DAY = "2026-10-24"
MIDNIGHT = datetime(2026, 10, 24)
CAPTURED = datetime(2026, 10, 25, 12)


def service():
    assert importlib.util.find_spec("daylens.services.day_activity_service") is not None
    return importlib.import_module("daylens.services.day_activity_service")


def row(identifier="a", start=36000, duration=300, **overrides):
    value = {
        "id": identifier, "session_id": identifier, "date": DAY,
        "start_time": (MIDNIGHT + timedelta(seconds=start)).isoformat(sep=" "),
        "end_time": (MIDNIGHT + timedelta(seconds=start + duration)).isoformat(sep=" "),
        "process_name": "editor.exe", "window_title": "raw title",
        "normalized_title": "project", "category_key": "coding",
        "category_name": "编程", "duration_seconds": duration,
        "effective_seconds": duration, "engaged_seconds": duration,
        "passive_seconds": 0, "idle_seconds": 0,
        "metric_version": "attention-v1", "classification_version": "rules-v1",
    }
    value.update(overrides)
    return value


def build(rows, day=DAY, **kwargs):
    return service().build_day_activity(rows, day, captured_at=CAPTURED, **kwargs)


def test_day_activity_service_is_available():
    assert service() is not None


@pytest.mark.parametrize("seconds,is_long", [(299, False), (300, True), (301, True)])
def test_long_event_threshold_uses_effective_counter(seconds, is_long):
    result = build([row(duration=seconds)])
    assert result["events"][0]["is_long"] is is_long
    assert result["totals"]["effective_seconds"] == seconds


def test_passive_video_is_long_and_mixed_idle_not_located_inside_row():
    result = build([row(duration=600, effective_seconds=300, engaged_seconds=0,
                        passive_seconds=300, idle_seconds=300, category_key="video")])
    event = result["events"][0]
    assert event["is_long"] and event["contains_idle"]
    assert event["duration_seconds"] == 600
    assert event["passive_seconds"] == 300
    assert [s["kind"] for s in result["segments"]] == ["missing", "activity", "missing"]


def test_contiguous_identical_evidence_groups_and_resolves_display_once_per_event():
    calls = []
    def resolve(process, details):
        calls.append((process, details))
        return "Editor"
    rows = [row("a", duration=150), row("b", start=36151, duration=150)]
    original = deepcopy(rows)
    result = build(rows, resolve_display=resolve)
    assert rows == original
    assert len(result["events"]) == 1
    event = result["events"][0]
    assert event["app"] == "Editor" and event["is_long"]
    assert event["effective_seconds"] == 300
    assert event["end_second"] - event["start_second"] == 301
    assert event["source_session_ids"] == ["a", "b"]
    assert calls[0][0] == "editor.exe" and calls[0][1]
    assert build(rows)["events"][0]["id"] == event["id"]


@pytest.mark.parametrize("changed", [
    {"process_name": "other.exe"}, {"normalized_title": "other"},
    {"category_key": "reading"}, {"metric_version": "attention-v2"},
    {"classification_version": "rules-v2"},
])
def test_evidence_boundaries_do_not_group(changed):
    assert len(build([row(duration=150), row("b", start=36150, duration=150, **changed)])["events"]) == 2


def test_gaps_and_switch_return_do_not_group():
    assert len(build([row(duration=150), row("b", start=36153, duration=150)])["events"]) == 2
    rows = [row(duration=149), row("b", start=36149, duration=1, process_name="other"),
            row("c", start=36150, duration=150)]
    assert len(build(rows)["events"]) == 3


def test_seam_tolerance_respects_sample_interval_and_two_second_cap():
    rows = [row(duration=150), row("b", start=36152, duration=150)]
    assert len(build(rows, sample_interval=10)["events"]) == 1
    assert len(build(rows, sample_interval=1)["events"]) == 2
    rows[1] = row("b", start=36153, duration=150)
    assert len(build(rows, sample_interval=10)["events"]) == 2


def test_explicit_idle_breaks_groups_and_zero_effective_nonidle_is_activity():
    rows = [row(duration=150), row("idle", start=36150, duration=1, category_key="idle",
            effective_seconds=0, engaged_seconds=0, idle_seconds=1),
            row("c", start=36151, duration=150),
            row("d", start=36500, duration=10, effective_seconds=0, engaged_seconds=0,
                passive_seconds=0, idle_seconds=10)]
    result = build(rows)
    assert len(result["events"]) == 4
    assert [s["kind"] for s in result["segments"]].count("idle") == 1
    assert result["segments"][-2]["kind"] == "activity"


def test_midnight_clipping_conserves_all_integer_counters():
    crossing = row(start=-2, duration=5, effective_seconds=3, engaged_seconds=2,
                   passive_seconds=1, idle_seconds=2)
    previous = build([crossing], day="2026-10-23")
    current = build([crossing])
    for field in ("effective_seconds", "engaged_seconds", "passive_seconds", "idle_seconds"):
        assert previous["totals"][field] + current["totals"][field] == crossing[field]
    assert sum(result["events"][0]["duration_seconds"] for result in [previous, current]) == 5
    assert current["events"][0]["start_second"] == 0


def test_exact_duplicate_ids_deduplicate_but_conflicts_are_unreliable():
    original = row()
    result = build([original, deepcopy(original)])
    assert result["totals"]["effective_seconds"] == 300
    conflict = row(effective_seconds=299, engaged_seconds=299, idle_seconds=1)
    result = build([original, conflict, row("safe", start=40000)])
    assert result["status"] == "partial" and result["warnings"]
    assert [event["source_session_ids"] for event in result["events"]] == [["safe"]]
    assert result["totals"]["effective_seconds"] == 300
    assert "unreliable" in [segment["kind"] for segment in result["segments"]]


def test_chain_overlaps_exclude_every_conflicting_row_not_nonoverlap():
    result = build([row("a", start=10, duration=10), row("b", start=15, duration=10),
                    row("c", start=24, duration=10), row("safe", start=40, duration=10)])
    assert result["totals"]["effective_seconds"] == 10
    assert [event["source_session_ids"] for event in result["events"]] == [["safe"]]
    assert result["segments"][1] == {"kind": "unreliable", "start_second": 10,
                                     "end_second": 34, "event_id": None}


@pytest.mark.parametrize("bad", [
    {"start_time": "bad"}, {"end_time": "2026-10-24 09:00:00"},
    {"effective_seconds": -1}, {"duration_seconds": 302, "effective_seconds": 302, "engaged_seconds": 302},
    {"effective_seconds": 301}, {"engaged_seconds": "nan"},
])
def test_invalid_rows_produce_partial_not_credible_zero(bad):
    result = build([row(**bad)])
    assert result["status"] == "partial" and result["warnings"]
    assert result["events"] == []


def test_empty_past_today_future_and_complete_segment_coverage():
    past = build([])
    assert past["status"] == "empty"
    assert past["segments"] == [{"kind": "missing", "start_second": 0, "end_second": 86400, "event_id": None}]
    today = build([], day="2026-10-25")
    assert [s["kind"] for s in today["segments"]] == ["missing", "future"]
    assert today["segments"][1]["start_second"] == 43200
    assert build([], day="2026-10-26")["segments"][0]["kind"] == "future"


def test_today_counters_clip_at_capture_without_counting_future():
    result = build([row(start=43199, duration=4)], day="2026-10-24")
    assert result["totals"]["effective_seconds"] == 4
    result = service().build_day_activity([row(start=43199, duration=4)], DAY,
                                          captured_at=datetime(2026, 10, 24, 12))
    assert result["totals"]["effective_seconds"] == 1
    assert result["events"][0]["end_second"] == 43200
    assert result["segments"][-1]["kind"] == "future"


def test_legacy_preserves_effective_but_never_fabricates_engaged_passive():
    result = build([row(metric_version="legacy", effective_seconds=120,
                        engaged_seconds=0, passive_seconds=0)])
    event = result["events"][0]
    assert event["legacy"] and event["effective_seconds"] == 120
    assert event["engaged_seconds"] is None and event["passive_seconds"] is None
    assert result["totals"]["engaged_seconds"] is None
    assert result["warnings"] and result["status"] == "partial"


def test_loader_called_exactly_once_with_full_day_interval_and_failures_contained():
    calls = []
    def loader(*args):
        calls.append(args)
        return [row()]
    result = service().load_day_activity("synthetic.db", DAY, captured_at=CAPTURED, session_loader=loader)
    assert calls == [("synthetic.db", "2026-10-24 00:00:00", "2026-10-25 00:00:00")]
    assert result["last_recorded_at"] == "2026-10-24T10:05:00"
    def broken(*args):
        raise sqlite3.OperationalError("locked")
    result = service().load_day_activity("synthetic.db", DAY, captured_at=CAPTURED, session_loader=broken)
    assert result["status"] == "unavailable" and result["warnings"]


def test_interval_query_reads_crossing_day_without_schema_or_data_changes(tmp_path):
    from daylens.repositories.connection_repository import SCHEMA
    db_path = tmp_path / "only-temp.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        data = row(start=-2, duration=5, date="wrong-stored-date")
        data.pop("id")
        keys = list(data)
        connection.execute(f"INSERT INTO activity_sessions ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})", list(data.values()))
    before = db_path.read_bytes()
    result = service().load_day_activity(str(db_path), DAY, captured_at=CAPTURED)
    assert result["events"][0]["start_second"] == 0
    assert result["totals"]["effective_seconds"] == 3
    assert db_path.read_bytes() == before


def test_missing_database_is_not_created_and_old_schema_is_not_migrated(tmp_path):
    missing = tmp_path / "absent.db"
    assert service().load_day_activity(str(missing), DAY, captured_at=CAPTURED)["status"] == "unavailable"
    assert not missing.exists()
    old = tmp_path / "old.db"
    with sqlite3.connect(old) as connection:
        connection.execute("CREATE TABLE activity_sessions(session_id TEXT)")
    before = old.read_bytes()
    assert service().load_day_activity(str(old), DAY, captured_at=CAPTURED)["status"] == "unavailable"
    assert old.read_bytes() == before


def test_one_sampling_interval_counter_overhead_is_not_a_false_anomaly():
    result = build([row(duration_seconds=301, effective_seconds=301, engaged_seconds=301)])
    assert result["status"] == "ready"
    assert result["totals"]["effective_seconds"] == 301
    assert build([row(duration_seconds=302, effective_seconds=302, engaged_seconds=302)],
                 sample_interval=2)["status"] == "ready"


def test_interval_query_surfaces_malformed_selected_day_rows_in_same_read(tmp_path):
    from daylens.repositories.connection_repository import SCHEMA
    db_path = tmp_path / "malformed-temp.db"
    with sqlite3.connect(db_path) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO activity_sessions(session_id, start_time, end_time, date) VALUES ('bad', 'broken', 'broken', ?)", (DAY,))
        connection.execute("INSERT INTO activity_sessions(session_id, start_time, end_time, date) VALUES ('bad-other-day', 'broken', 'broken', '2020-01-01')")
    before = db_path.read_bytes()
    result = service().load_day_activity(str(db_path), DAY, captured_at=CAPTURED)
    assert result["status"] == "partial" and result["warnings"]
    assert result["events"] == []
    assert db_path.read_bytes() == before


def test_missing_normalized_title_uses_exact_raw_title_boundary():
    rows = [row(duration=150, normalized_title="", window_title="document one"),
            row("b", start=36150, duration=150, normalized_title="", window_title="document two")]
    result = build(rows)
    assert len(result["events"]) == 2
    assert [event["title"] for event in result["events"]] == ["document one", "document two"]


def test_title_whitespace_is_normalized_consistently_for_display_and_grouping():
    rows = [row(duration=150, normalized_title=" ", window_title="  document   one \n"),
            row("b", start=36150, duration=150, normalized_title="", window_title="document one")]
    result = build(rows)
    assert len(result["events"]) == 1
    assert result["events"][0]["title"] == "document one"


def test_integer_valued_numeric_text_does_not_crash_other_valid_evidence():
    result = build([row(duration_seconds="300.0", effective_seconds="3e2", engaged_seconds="300.0")])
    assert result["status"] == "ready"
    assert result["events"][0]["effective_seconds"] == 300


def _assert_consistent_day_partitions(source):
    fields = ("duration_seconds", "effective_seconds", "engaged_seconds",
              "passive_seconds", "idle_seconds")
    sums = {field: 0 for field in fields}
    day_start = datetime.fromisoformat(source["start_time"]).replace(hour=0, minute=0, second=0)
    end = datetime.fromisoformat(source["end_time"])
    day_count = 0
    while day_start < end:
        result = service().build_day_activity([source], day_start.date().isoformat(),
                                             captured_at=datetime(2026, 11, 10))
        assert result["status"] == "ready", result["warnings"]
        assert len(result["events"]) == 1
        event = result["events"][0]
        assert event["duration_seconds"] == event["effective_seconds"] + event["idle_seconds"]
        assert event["effective_seconds"] == event["engaged_seconds"] + event["passive_seconds"]
        for field in fields:
            assert 0 <= event[field] <= source[field]
            sums[field] += event[field]
        day_start += timedelta(days=1)
        day_count += 1
    assert sums == {field: source[field] for field in fields}
    return day_count


def test_two_second_midnight_split_preserves_each_days_attention_composition():
    source = row(start=-1, duration=2, effective_seconds=2, engaged_seconds=1,
                 passive_seconds=1, idle_seconds=0)
    assert _assert_consistent_day_partitions(source) == 2


@pytest.mark.parametrize("span,duration,effective,engaged", [
    (2, 0, 0, 0), (2, 2, 0, 0), (2, 3, 2, 1),
    (5, 5, 3, 1), (5, 5, 4, 3), (7, 7, 5, 2), (7, 8, 7, 3),
])
def test_midnight_split_keeps_mixed_zero_and_sampling_overhead_counters(
        span, duration, effective, engaged):
    source = row(start=-1, duration=span, duration_seconds=duration,
                 effective_seconds=effective, engaged_seconds=engaged,
                 passive_seconds=effective - engaged, idle_seconds=duration - effective)
    assert _assert_consistent_day_partitions(source) == 2


def test_deterministic_multiday_splits_preserve_composition_and_every_source_counter():
    generator = random.Random(2741)
    for _ in range(160):
        span = generator.randrange(2 * 86400 + 1, 4 * 86400)
        duration = span + generator.choice([0, 0, 1])
        effective = generator.randrange(duration + 1)
        engaged = generator.randrange(effective + 1)
        source = row(start=generator.randrange(86400), duration=span,
                     duration_seconds=duration, effective_seconds=effective,
                     engaged_seconds=engaged, passive_seconds=effective - engaged,
                     idle_seconds=duration - effective)
        assert _assert_consistent_day_partitions(source) >= 3


def test_split_legacy_inexact_composition_preserves_raw_totals_and_unknown_attention():
    source = row(start=-1, duration=4, effective_seconds=1,
                 engaged_seconds=0, passive_seconds=0, idle_seconds=1,
                 metric_version="legacy")
    parts = [build([source], day="2026-10-23"), build([source])]
    for part in parts:
        assert part["status"] == "partial" and part["warnings"]
        assert part["events"][0]["engaged_seconds"] is None
        assert part["events"][0]["passive_seconds"] is None
    for field in ("duration_seconds", "effective_seconds", "idle_seconds"):
        assert sum(part["events"][0][field] for part in parts) == source[field]
