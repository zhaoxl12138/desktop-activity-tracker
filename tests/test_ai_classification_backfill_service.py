from __future__ import annotations

import json
import sqlite3

from daylens.repositories.connection_repository import init_db
from daylens.services.ai_classification_backfill_service import (
    apply_ai_classification_backfill,
)


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
    process="Hades2.exe",
    raw_title="Hades II",
    normalized_title="Hades II",
    category="other",
    classification_version="rules-old",
    times=(46, 46, 46, 0, 0),
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
                identity, f"{day} 16:51:03", f"{day} 16:51:49", day,
                process, raw_title, normalized_title, category, "其他",
                "interactive_required", duration, effective, engaged,
                passive, idle, "engagement-v2", classification_version,
            ),
        )


def _rows(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            row["session_id"]: dict(row)
            for row in conn.execute(
                "SELECT * FROM activity_sessions ORDER BY session_id"
            )
        }


def _rules(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {
            row["category_key"]: dict(row)
            for row in conn.execute("SELECT * FROM custom_rules")
        }


def test_high_confidence_ai_backfills_only_exact_today_fallback_and_moves_rule(tmp_path):
    db = _database(tmp_path)
    _insert_session(db, "target")
    _insert_session(db, "same-title-browser-fallback", category="browser_general")
    _insert_session(db, "different-title", normalized_title="Settings")
    _insert_session(db, "previous-day", day="2026-10-27")
    _insert_session(db, "different-app", process="other.exe")
    _insert_session(db, "already-classified", category="reading")
    _insert_session(
        db, "manual-other", classification_version="manual-correction-v1"
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            """INSERT INTO custom_rules (
                   category_key, display_name, active_rule, process_names,
                   title_keywords, title_patterns, process_names_mode,
                   title_keywords_mode, title_patterns_mode
               ) VALUES ('other', '其他', 'interactive_required',
                         'Hades2.exe\nkeep.exe', '', '',
                         'replace', 'inherit', 'inherit')"""
        )

    before = {
        identity: {
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            **{field: row[field] for field in TIME_FIELDS},
        }
        for identity, row in _rows(db).items()
    }

    result = apply_ai_classification_backfill(
        db_path=str(db),
        process_name="Hades2.exe",
        window_title="Hades II",
        normalized_title="Hades II",
        category_key="gaming",
        categories={},
        day="2026-10-28",
    )

    assert result.updated_sessions == 2
    assert result.updated_effective_seconds == 92
    assert result.rule_changed is True
    assert result.shared_browser is False
    assert result.time_conserved is True
    rows = _rows(db)
    for identity in ("target", "same-title-browser-fallback"):
        assert (
            rows[identity]["category_key"],
            rows[identity]["category_name"],
            rows[identity]["active_rule"],
            rows[identity]["classification_version"],
        ) == (
            "gaming", "游戏娱乐", "interactive_required",
            "ai-high-backfill-v1",
        )
    for identity in (
        "different-title", "previous-day", "different-app",
        "already-classified", "manual-other",
    ):
        assert rows[identity]["category_key"] in {
            "other", "reading",
        }
    assert {
        identity: {
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            **{field: row[field] for field in TIME_FIELDS},
        }
        for identity, row in rows.items()
    } == before

    rules = _rules(db)
    assert rules["other"]["process_names"].splitlines() == ["keep.exe"]
    assert rules["gaming"]["process_names"].splitlines() == ["Hades2.exe"]
    audit = json.loads(open(result.audit_path, encoding="utf-8").read())
    assert audit["operation"] == "ai_high_confidence_backfill"
    assert audit["updated_sessions"] == 2
    assert not ({"title", "window_title", "normalized_title"} & set(audit))


def test_high_confidence_browser_backfills_title_without_process_rule(tmp_path):
    db = _database(tmp_path)
    _insert_session(
        db, "browser", process="chrome.exe",
        raw_title="Course - Google Chrome", normalized_title="Course",
        category="browser_general",
    )

    result = apply_ai_classification_backfill(
        db_path=str(db), process_name="chrome.exe",
        window_title="Course - Google Chrome", normalized_title="Course",
        category_key="reading", categories={}, day="2026-10-28",
    )

    assert result.updated_sessions == 1
    assert result.shared_browser is True
    assert result.rule_changed is False
    assert _rows(db)["browser"]["category_key"] == "reading"
    assert all(
        "chrome.exe" not in row["process_names"].casefold()
        for row in _rules(db).values()
    )


def test_high_confidence_backfill_is_idempotent(tmp_path):
    db = _database(tmp_path)
    _insert_session(db, "target")
    kwargs = dict(
        db_path=str(db), process_name="Hades2.exe",
        window_title="Hades II", normalized_title="Hades II",
        category_key="gaming", categories={}, day="2026-10-28",
    )

    first = apply_ai_classification_backfill(**kwargs)
    second = apply_ai_classification_backfill(**kwargs)

    assert first.updated_sessions == 1
    assert first.rule_changed is True
    assert second.updated_sessions == 0
    assert second.updated_effective_seconds == 0
    assert second.rule_changed is False

