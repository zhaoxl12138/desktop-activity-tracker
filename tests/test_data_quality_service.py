import sqlite3

from daylens.services.data_quality_service import inspect_data_quality


def test_inspect_data_quality_reports_duration_mismatch(tmp_path):
    db = tmp_path / "quality.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE activity_sessions (session_id TEXT, start_time TEXT, end_time TEXT, date TEXT, duration_seconds INTEGER, effective_seconds INTEGER, idle_seconds INTEGER)")
    conn.execute("INSERT INTO activity_sessions VALUES ('s1','2026-01-01 10:00','2026-01-01 10:10','2026-01-01',10,8,5)")
    conn.commit(); conn.close()

    result = inspect_data_quality(str(db), "2026-01-01")

    assert result["issue_count"] == 1
    assert result["issues"][0]["type"] == "duration_mismatch"
