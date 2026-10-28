from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from daylens import database
from daylens.services.historical_category_repair_service import (
    apply_repair,
    preview_repair,
)


def _seed_database(path: Path) -> None:
    conn = database.init_db(str(path))
    rows = [
        ("game", "2026-10-08", "LostCastle2.exe", "LostCastle2", "other", "其他", 120, 100, 100, 0, 20),
        ("finance", "2026-10-09", "hexin.exe", "同花顺", "other", "其他", 90, 60, 60, 0, 30),
        ("correct", "2026-10-10", "LostCastle2.exe", "LostCastle2", "gaming", "游戏娱乐", 70, 70, 70, 0, 0),
        ("outside", "2026-09-28", "LostCastle2.exe", "LostCastle2", "other", "其他", 50, 50, 50, 0, 0),
        ("ambiguous", "2026-10-11", "unknown.exe", "Private title", "other", "其他", 40, 20, 20, 0, 20),
    ]
    for sid, day, process, title, key, name, duration, effective, engaged, passive, idle in rows:
        conn.execute(
            """
            INSERT INTO activity_sessions
                (session_id,start_time,end_time,date,process_name,window_title,
                 normalized_title,category_key,category_name,active_rule,
                 duration_seconds,effective_seconds,engaged_seconds,
                 passive_seconds,idle_seconds,metric_version,classification_version)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                sid, f"{day} 10:00:00", f"{day} 10:02:00", day, process,
                title, title, key, name, "interactive_required", duration,
                effective, engaged, passive, idle, "attention-v1", "rules-old",
            ),
        )
    conn.commit()
    database.close_db(conn)


def _time_totals(path: Path) -> tuple[int, ...]:
    with sqlite3.connect(path) as conn:
        return tuple(conn.execute(
            """
            SELECT COALESCE(SUM(duration_seconds),0),
                   COALESCE(SUM(effective_seconds),0),
                   COALESCE(SUM(engaged_seconds),0),
                   COALESCE(SUM(passive_seconds),0),
                   COALESCE(SUM(idle_seconds),0)
            FROM activity_sessions
            """
        ).fetchone())


def test_preview_is_read_only_and_reports_only_deterministic_other_rows(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    _seed_database(db_path)
    before = db_path.read_bytes()

    preview = preview_repair(str(db_path), "2026-09-29", "2026-10-28")

    assert preview["total_rows"] == 2
    assert preview["groups"]["gaming"]["rows"] == 1
    assert preview["groups"]["finance"]["rows"] == 1
    assert preview["time_totals"] == {
        "duration_seconds": 210,
        "effective_seconds": 160,
        "engaged_seconds": 160,
        "passive_seconds": 0,
        "idle_seconds": 50,
    }
    assert db_path.read_bytes() == before
    assert list(tmp_path.glob("*.json")) == []


def test_apply_backs_up_updates_rules_audits_and_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "usage.db"
    backup_dir = tmp_path / "backups"
    audit_dir = tmp_path / "logs"
    _seed_database(db_path)
    before_totals = _time_totals(db_path)

    result = apply_repair(
        str(db_path), "2026-09-29", "2026-10-28",
        backup_dir=backup_dir,
        audit_dir=audit_dir,
        timestamp="20261028-120000",
    )

    assert result["changed_rows"] == 2
    backup_path = Path(result["backup_path"])
    audit_path = Path(result["audit_path"])
    assert backup_path.is_file()
    assert audit_path.is_file()
    assert _time_totals(db_path) == before_totals

    with sqlite3.connect(db_path) as conn:
        rows = dict(conn.execute(
            "SELECT session_id, category_key FROM activity_sessions"
        ).fetchall())
        assert rows == {
            "game": "gaming", "finance": "finance", "correct": "gaming",
            "outside": "other", "ambiguous": "other",
        }
        rules = {
            key: processes
            for key, processes in conn.execute(
                "SELECT category_key, process_names FROM custom_rules WHERE category_key IN ('gaming','finance')"
            )
        }
    assert "LostCastle2.exe" in rules["gaming"].splitlines()
    assert "hexin.exe" in rules["finance"].splitlines()

    audit = json.loads(audit_path.read_text(encoding="utf-8"))
    assert audit["changed_rows"] == 2
    assert "Private title" not in audit_path.read_text(encoding="utf-8")
    assert audit["time_conserved"] is True

    second = apply_repair(
        str(db_path), "2026-09-29", "2026-10-28",
        backup_dir=backup_dir,
        audit_dir=audit_dir,
        timestamp="20261028-120100",
    )
    assert second["changed_rows"] == 0
    assert _time_totals(db_path) == before_totals
