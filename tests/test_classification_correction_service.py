from __future__ import annotations

import json
import sqlite3
from datetime import date

import pytest

from daylens.repositories.connection_repository import init_db
from daylens.services.classification_correction_service import (
    apply_classification_correction,
)
from daylens.services.intelligence_state import load_overrides


TIME_FIELDS = (
    "duration_seconds",
    "effective_seconds",
    "engaged_seconds",
    "passive_seconds",
    "idle_seconds",
)


def _database(tmp_path):
    path = tmp_path / "usage.db"
    init_db(str(path)).close()
    return path


def _insert_session(
    db_path,
    identity,
    *,
    day="2026-10-28",
    process="Probably Stolen.exe",
    raw_title="Probably Stolen",
    normalized_title="Probably Stolen",
    category="other",
    times=(420, 390, 360, 30, 30),
):
    duration, effective, engaged, passive, idle = times
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO activity_sessions (
                session_id, start_time, end_time, date, process_name,
                window_title, normalized_title, category_key, category_name,
                active_rule, duration_seconds, effective_seconds,
                engaged_seconds, passive_seconds, idle_seconds,
                metric_version, classification_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                identity,
                f"{day} 10:00:00",
                f"{day} 10:07:00",
                day,
                process,
                raw_title,
                normalized_title,
                category,
                "其他",
                "interactive_required",
                duration,
                effective,
                engaged,
                passive,
                idle,
                "engagement-v2",
                "rules-old",
            ),
        )


def _session_rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return [dict(row) for row in conn.execute(
            "SELECT * FROM activity_sessions ORDER BY session_id"
        )]


def _custom_rules(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            row["category_key"]: dict(row)
            for row in conn.execute("SELECT * FROM custom_rules")
        }


def test_ordinary_app_correction_updates_only_exact_today_and_moves_process_rule(tmp_path):
    db = _database(tmp_path)
    _insert_session(db, "a")
    _insert_session(db, "b", times=(120, 120, 120, 0, 0))
    _insert_session(db, "different-title", normalized_title="Settings")
    _insert_session(db, "previous-day", day="2026-10-27")
    _insert_session(db, "different-app", process="other.exe")
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO custom_rules (
                   category_key, display_name, active_rule, process_names,
                   title_keywords, title_patterns, process_names_mode,
                   title_keywords_mode, title_patterns_mode
               ) VALUES ('other', '其他', 'interactive_required',
                         'Probably Stolen.exe\nkeep.exe', 'keep-title', '',
                         'replace', 'replace', 'inherit')"""
        )

    before = {
        row["session_id"]: tuple(row[field] for field in TIME_FIELDS)
        for row in _session_rows(db)
    }
    result = apply_classification_correction(
        db_path=str(db),
        intelligence_dir=tmp_path / "intelligence",
        process_name="Probably Stolen.exe",
        window_title="Probably Stolen",
        normalized_title="Probably Stolen",
        category_key="gaming",
        categories={},
        day=date(2026, 10, 28),
        scope="similar",
    )

    assert result.updated_sessions == 2
    assert result.rule_changed is True
    assert result.shared_browser is False
    assert result.time_conserved is True
    rows = {row["session_id"]: row for row in _session_rows(db)}
    for identity in ("a", "b"):
        assert (
            rows[identity]["category_key"],
            rows[identity]["category_name"],
            rows[identity]["active_rule"],
            rows[identity]["classification_version"],
        ) == ("gaming", "游戏娱乐", "interactive_required", "manual-correction-v1")
    for identity in ("different-title", "previous-day", "different-app"):
        assert rows[identity]["category_key"] == "other"
    assert {
        identity: tuple(row[field] for field in TIME_FIELDS)
        for identity, row in rows.items()
    } == before

    rules = _custom_rules(db)
    assert rules["other"]["process_names"].splitlines() == ["keep.exe"]
    assert rules["other"]["title_keywords"] == "keep-title"
    assert rules["other"]["process_names_mode"] == "replace"
    assert rules["gaming"]["process_names"].splitlines() == ["Probably Stolen.exe"]
    assert rules["gaming"]["process_names_mode"] == "inherit"
    assert next(iter(load_overrides(tmp_path / "intelligence").values()))["category"] == "gaming"
    audit = json.loads(open(result.audit_path, encoding="utf-8").read())
    assert audit["updated_sessions"] == 2
    assert not ({"title", "window_title", "normalized_title"} & set(audit))


@pytest.mark.parametrize(
    "process",
    ["chrome.exe", "360ChromeX.exe", "msedge.exe", "firefox.exe"],
)
def test_shared_browser_correction_never_creates_process_rule(tmp_path, process):
    db = _database(tmp_path)
    _insert_session(db, "browser", process=process, raw_title="Course - Browser", normalized_title="Course")

    first = apply_classification_correction(
        db_path=str(db), intelligence_dir=tmp_path / "intelligence",
        process_name=process, window_title="Course - Browser",
        normalized_title="Course", category_key="reading", categories={},
        day=date(2026, 10, 28), scope="similar",
    )
    second = apply_classification_correction(
        db_path=str(db), intelligence_dir=tmp_path / "intelligence",
        process_name=process, window_title="Course - Browser",
        normalized_title="Course", category_key="reading", categories={},
        day=date(2026, 10, 28), scope="similar",
    )

    assert first.updated_sessions == 1
    assert first.shared_browser is True
    assert first.rule_changed is False
    assert second.updated_sessions == 0
    assert second.rule_changed is False
    assert all(process.casefold() not in row["process_names"].casefold()
               for row in _custom_rules(db).values())


def test_missing_normalized_title_uses_existing_title_normalizer(tmp_path):
    db = _database(tmp_path)
    _insert_session(
        db, "fallback", process="chrome.exe",
        raw_title="Course - Google Chrome", normalized_title="",
    )
    result = apply_classification_correction(
        db_path=str(db), intelligence_dir=tmp_path / "intelligence",
        process_name="chrome.exe", window_title="Course - Google Chrome",
        normalized_title="Course", category_key="reading", categories={},
        day=date(2026, 10, 28), scope="exact",
    )
    assert result.updated_sessions == 1


def test_state_save_failure_restores_sessions_and_custom_rules(tmp_path, monkeypatch):
    from daylens.services import classification_correction_service as service

    db = _database(tmp_path)
    _insert_session(db, "a")
    before_rows = _session_rows(db)
    before_rules = _custom_rules(db)

    def fail(*_args, **_kwargs):
        raise OSError("state unavailable")

    monkeypatch.setattr(service, "save_override", fail)
    with pytest.raises(OSError, match="state unavailable"):
        apply_classification_correction(
            db_path=str(db), intelligence_dir=tmp_path / "intelligence",
            process_name="Probably Stolen.exe", window_title="Probably Stolen",
            normalized_title="Probably Stolen", category_key="gaming",
            categories={}, day=date(2026, 10, 28), scope="similar",
        )

    assert _session_rows(db) == before_rows
    assert _custom_rules(db) == before_rules

