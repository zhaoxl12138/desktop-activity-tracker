from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from daylens import database
from daylens.services.rule_usage_service import load_rule_usage_snapshot


def _categories() -> dict[str, dict]:
    return {
        "coding": {
            "display_name": "编程开发",
            "match": {
                "process_names": ["Code.exe", "CODE.EXE", "python.exe", "learned.exe"]
            },
        },
        "gaming": {
            "display_name": "游戏娱乐",
            "match": {"process_names": ["factory-game.exe"]},
        },
    }


def _factory_categories() -> dict[str, dict]:
    return {
        "coding": {
            "match": {"process_names": ["Code.exe", "python.exe"]},
        },
        "gaming": {
            "match": {"process_names": ["factory-game.exe"]},
        },
    }


def _insert_session(db_path, *, process: str, day: str, effective: int) -> None:
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO activity_sessions (
                session_id, start_time, end_time, date, process_name,
                category_key, category_name, active_rule,
                duration_seconds, effective_seconds, engaged_seconds
            ) VALUES (?, ?, ?, ?, ?, 'coding', '编程开发',
                      'interactive_required', ?, ?, ?)
            """,
            (
                f"{process}-{day}-{effective}",
                f"{day} 10:00:00",
                f"{day} 10:01:00",
                day,
                process,
                effective,
                effective,
                effective,
            ),
        )


def test_snapshot_shows_recent_and_learned_rules_but_hides_unused_factory(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    today = date(2026, 10, 28)
    _insert_session(
        db_path,
        process="code.exe",
        day=(today - timedelta(days=3)).isoformat(),
        effective=120,
    )
    _insert_session(
        db_path,
        process="python.exe",
        day=(today - timedelta(days=45)).isoformat(),
        effective=600,
    )

    snapshot = load_rule_usage_snapshot(
        str(db_path),
        _categories(),
        _factory_categories(),
        today=today,
    )

    coding = snapshot.categories["coding"]
    assert [item.process_name for item in coding.visible_processes] == [
        "Code.exe",
        "learned.exe",
    ]
    assert coding.visible_processes[0].hits == 1
    assert coding.visible_processes[0].effective_seconds == 120
    assert coding.visible_processes[0].source == "recent"
    assert coding.visible_processes[1].source == "learned"
    assert coding.hidden_factory_count == 1
    assert coding.hits == 1
    assert coding.effective_seconds == 120
    assert coding.last_seen == (today - timedelta(days=3)).isoformat()
    assert snapshot.categories["gaming"].visible_processes == ()
    assert snapshot.categories["gaming"].hidden_factory_count == 1


def test_snapshot_without_any_history_keeps_factory_rules_visible(tmp_path):
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()

    snapshot = load_rule_usage_snapshot(
        str(db_path), _categories(), _factory_categories(), today=date(2026, 10, 28)
    )

    assert snapshot.has_history is False
    assert [
        item.process_name for item in snapshot.categories["coding"].visible_processes
    ] == ["Code.exe", "python.exe", "learned.exe"]
    assert snapshot.categories["coding"].hidden_factory_count == 0


def test_snapshot_query_failure_degrades_to_complete_rule_list(tmp_path):
    db_path = tmp_path / "not-initialized.db"

    snapshot = load_rule_usage_snapshot(
        str(db_path), _categories(), _factory_categories(), today=date(2026, 10, 28)
    )

    assert snapshot.degraded is True
    assert [
        item.process_name for item in snapshot.categories["gaming"].visible_processes
    ] == ["factory-game.exe"]
    assert snapshot.categories["gaming"].hidden_factory_count == 0

