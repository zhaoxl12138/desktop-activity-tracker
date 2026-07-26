import sqlite3
from pathlib import Path

import pytest

from daylens import database
from daylens.services import data_quality_service
from daylens.services.data_quality_service import inspect_data_quality
from daylens.services.session_runtime_service import SessionRuntimeStore
from daylens.session_tracker import SessionTracker


def test_inspect_data_quality_reports_duration_mismatch(tmp_path):
    db = tmp_path / "quality.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE activity_sessions (session_id TEXT, start_time TEXT, end_time TEXT, date TEXT, duration_seconds INTEGER, effective_seconds INTEGER, idle_seconds INTEGER)")
    conn.execute("INSERT INTO activity_sessions VALUES ('s1','2026-01-01 10:00:00','2026-01-01 10:00:10','2026-01-01',10,8,5)")
    conn.commit(); conn.close()

    result = inspect_data_quality(str(db), "2026-01-01")

    assert result["issue_count"] == 1
    assert result["issues"][0]["type"] == "duration_mismatch"


def _create_quality_database(tmp_path):
    db = tmp_path / "quality.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE activity_sessions ("
        "session_id TEXT, start_time TEXT, end_time TEXT, date TEXT, "
        "duration_seconds INTEGER, effective_seconds INTEGER, idle_seconds INTEGER"
        ")"
    )
    return db, conn


def test_inspect_data_quality_reports_unattributed_duration(tmp_path):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('missing','2026-01-02 10:00:00','2026-01-02 10:00:10',"
        "'2026-01-02',10,6,1)"
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["issue_count"] == 1
    assert result["issues"][0] == {
        "type": "duration_mismatch",
        "direction": "duration_exceeds_components",
        "session_id": "missing",
        "date": "2026-01-02",
        "impact_seconds": 3,
    }
    assert result["affected_dates"] == ["2026-01-02"]
    assert result["unattributed_seconds"] == 3
    assert result["impact_seconds"] == 3
    assert result["score"] < 100


def test_inspect_data_quality_reports_multiple_issues_for_one_row(tmp_path):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('multi','2026-01-03 10:00:00','2026-01-03 10:10:00',"
        "'2026-01-03',10,4,1)"
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["issue_count"] == 2
    assert {issue["type"] for issue in result["issues"]} == {
        "duration_mismatch",
        "wall_clock_mismatch",
    }
    assert result["affected_dates"] == ["2026-01-03"]
    assert result["unattributed_seconds"] == 5
    assert result["score"] == 0


def test_inspect_data_quality_reports_wall_clock_span_anomaly(tmp_path):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('wall','2026-01-04 10:00:00','2026-01-04 10:10:00',"
        "'2026-01-04',10,10,0)"
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["issue_count"] == 1
    assert result["issues"][0]["type"] == "wall_clock_mismatch"
    assert result["issues"][0]["impact_seconds"] == 590
    assert result["wall_clock_impact_seconds"] == 590


def test_inspect_data_quality_ignores_normal_two_minute_scheduling_drift(
    tmp_path,
):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('drift','2026-01-04 10:00:00','2026-01-04 10:02:00',"
        "'2026-01-04',10,10,0)"
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["issue_count"] == 0
    assert result["wall_clock_impact_seconds"] == 0


def test_inspect_data_quality_opens_existing_database_read_only(
    tmp_path, monkeypatch
):
    db, conn = _create_quality_database(tmp_path)
    conn.close()
    real_connect = sqlite3.connect
    opened = []

    def recording_connect(target, *args, **kwargs):
        opened.append((target, kwargs.copy()))
        return real_connect(target, *args, **kwargs)

    monkeypatch.setattr(data_quality_service.sqlite3, "connect", recording_connect)

    inspect_data_quality(str(db))

    assert len(opened) == 1
    target, kwargs = opened[0]
    assert target.startswith("file:")
    assert "mode=ro" in target
    assert kwargs["uri"] is True


def test_inspect_data_quality_allows_one_second_sampling_tolerance(tmp_path):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('tolerance','2026-01-05 10:00:00','2026-01-05 10:00:10',"
        "'2026-01-05',10,9,0)"
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["issue_count"] == 0
    assert result["score"] == 100


@pytest.mark.parametrize(
    ("component_delta", "expected_issue_count"),
    [(5, 0), (6, 1)],
)
def test_composition_tolerance_uses_actual_sample_interval(
    tmp_path,
    component_delta,
    expected_issue_count,
):
    db, conn = _create_quality_database(tmp_path)
    conn.execute(
        "INSERT INTO activity_sessions VALUES "
        "('sample-step','2026-01-05 10:00:00','2026-01-05 10:00:30',"
        "'2026-01-05',30,?,0)",
        (30 + component_delta,),
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(
        str(db),
        sample_interval_seconds=5,
    )

    duration_issues = [
        issue
        for issue in result["issues"]
        if issue["type"] == "duration_mismatch"
    ]
    assert len(duration_issues) == expected_issue_count


@pytest.mark.parametrize("sample_interval", [2, 60])
def test_tracker_first_sample_is_not_a_wall_clock_anomaly(
    tmp_path, monkeypatch, sample_interval
):
    monkeypatch.setattr("daylens.session_tracker._get_cursor_pos", lambda: (0, 0))
    monkeypatch.setattr(
        "daylens.session_tracker._get_keyboard_snapshot",
        lambda: bytes(256),
    )

    class CodingClassifier:
        def classify(self, _process_name, _window_title):
            return {
                "category_key": "coding",
                "category_name": "Coding",
                "active_rule": "interactive_required",
            }

    db_path = tmp_path / f"tracker-{sample_interval}.db"
    store = SessionRuntimeStore(str(db_path))
    tracker = SessionTracker(
        config={
            "tracker": {
                "sample_interval_seconds": sample_interval,
                "flush_interval_seconds": 999,
            }
        },
        classifier=CodingClassifier(),
        on_session_end=store.persist_session,
    )
    tracker.tick(
        0,
        {
            "process_name": "Code.exe",
            "window_title": "main.py",
            "exe_path": "",
            "pid": 1,
        },
    )
    tracker.finish_current("test")
    store.close()

    result = inspect_data_quality(
        str(db_path),
        sample_interval_seconds=sample_interval,
    )

    assert not [
        issue
        for issue in result["issues"]
        if issue["type"] == "wall_clock_mismatch"
    ]


def test_sparse_single_issue_never_rounds_score_up_to_100(tmp_path):
    db, conn = _create_quality_database(tmp_path)
    rows = [
        (
            f"clean-{index}",
            "2026-01-06 10:00:00",
            "2026-01-06 10:00:10",
            "2026-01-06",
            10,
            10,
            0,
        )
        for index in range(199)
    ]
    rows.append(
        (
            "broken",
            "2026-01-06 10:00:00",
            "2026-01-06 10:00:10",
            "2026-01-06",
            10,
            1,
            0,
        )
    )
    conn.executemany(
        "INSERT INTO activity_sessions VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()
    conn.close()

    result = inspect_data_quality(str(db))

    assert result["checked_sessions"] == 200
    assert result["issue_count"] == 1
    assert result["score"] <= 99


def _insert_session(
    conn,
    session_id: str,
    *,
    switch_reason: str,
    duration: int,
    effective: int,
    idle: int,
) -> None:
    conn.execute(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,process_name,category_key,
             category_name,duration_seconds,effective_seconds,idle_seconds,
             switch_reason)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            session_id,
            "2026-07-01 10:00:00",
            "2026-07-01 10:10:00",
            "2026-07-01",
            "QyClient.exe",
            "video",
            "娱乐休闲",
            duration,
            effective,
            idle,
            switch_reason,
        ),
    )


def _create_repairable_database(tmp_path: Path) -> Path:
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    conn = sqlite3.connect(db_path)
    _insert_session(
        conn,
        "legacy",
        switch_reason="entertainment_idle",
        duration=600,
        effective=600,
        idle=301,
    )
    conn.commit()
    conn.close()
    return db_path


def test_preview_repairable_sessions_only_selects_legacy_entertainment_idle(tmp_path):
    db_path = _create_repairable_database(tmp_path)
    conn = sqlite3.connect(db_path)
    _insert_session(
        conn,
        "other",
        switch_reason="app_change",
        duration=10,
        effective=8,
        idle=5,
    )
    conn.commit()
    conn.close()

    preview = data_quality_service.preview_repairable_sessions(str(db_path))

    assert preview["repairable_count"] == 1
    assert preview["dates"] == ["2026-07-01"]
    assert preview["duplicate_idle_seconds"] == 301


def test_repair_does_not_modify_database_when_backup_fails(tmp_path, monkeypatch):
    db_path = _create_repairable_database(tmp_path)
    monkeypatch.setattr(
        data_quality_service,
        "create_database_backup",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("backup failed")),
    )

    with pytest.raises(OSError, match="backup failed"):
        data_quality_service.repair_legacy_session_data(str(db_path))

    conn = sqlite3.connect(db_path)
    idle = conn.execute(
        "SELECT idle_seconds FROM activity_sessions WHERE session_id='legacy'"
    ).fetchone()[0]
    conn.close()
    assert idle == 301


def test_repair_creates_backup_and_repairs_matching_rows(tmp_path):
    db_path = _create_repairable_database(tmp_path)

    result = data_quality_service.repair_legacy_session_data(
        str(db_path),
        reason="manual-test",
    )

    assert result["repaired_count"] == 1
    assert Path(result["backup_path"]).is_file()
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT duration_seconds,effective_seconds,idle_seconds "
        "FROM activity_sessions WHERE session_id='legacy'"
    ).fetchone()
    conn.close()
    assert row == (600, 600, 0)


def test_auto_repair_runs_once(tmp_path):
    db_path = _create_repairable_database(tmp_path)

    first = data_quality_service.auto_repair_legacy_sessions(str(db_path))
    second = data_quality_service.auto_repair_legacy_sessions(str(db_path))

    assert first["status"] == "repaired"
    assert second["status"] == "already_completed"
    assert len(list((tmp_path / "backups").glob("*.db"))) == 1
