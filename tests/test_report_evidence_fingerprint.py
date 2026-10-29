import json
import sqlite3
from datetime import date

from daylens import database, exporter
from daylens.app_paths import AppPaths
from daylens.services.report_evidence_service import evidence_fingerprint, report_dates


def _insert(conn, category="other", version="rules-a"):
    conn.execute(
        """
        INSERT INTO activity_sessions (
            session_id,start_time,end_time,date,process_name,window_title,
            category_key,category_name,duration_seconds,effective_seconds,
            engaged_seconds,passive_seconds,idle_seconds,metric_version,
            classification_version
        ) VALUES ('s1','2026-10-20 09:00:00','2026-10-20 09:10:00',
                  '2026-10-20','app.exe','Title',?,?,600,600,600,0,0,
                  'attention-v1',?)
        """,
        (category, category, version),
    )
    conn.commit()


def test_report_fingerprint_changes_after_category_only_correction(tmp_path):
    db = tmp_path / "usage.db"
    conn = database.init_db(str(db))
    _insert(conn)
    before = evidence_fingerprint(str(db), "daily", ["2026-10-20"])

    conn.execute(
        "UPDATE activity_sessions SET category_key='gaming', "
        "category_name='游戏娱乐', classification_version='manual-correction-v1'"
    )
    conn.commit()
    after = evidence_fingerprint(str(db), "daily", ["2026-10-20"])
    conn.close()

    assert before != after


def test_report_fingerprint_uses_explicit_policy_and_source_columns(tmp_path):
    db = tmp_path / "usage.db"
    conn = database.init_db(str(db))
    _insert(conn)
    conn.execute(
        "UPDATE activity_sessions SET classification_policy_version=?, "
        "classification_source=?",
        ("policy-v1", "local_rule"),
    )
    conn.commit()
    before = evidence_fingerprint(str(db), "daily", ["2026-10-20"])

    conn.execute(
        "UPDATE activity_sessions SET classification_policy_version=?, "
        "classification_source=?",
        ("policy-v2", "manual"),
    )
    conn.commit()
    after = evidence_fingerprint(str(db), "daily", ["2026-10-20"])
    conn.close()

    assert before != after


def test_report_status_marks_ready_review_stale_when_evidence_changed(tmp_path, monkeypatch):
    db = tmp_path / "usage.db"
    conn = database.init_db(str(db))
    _insert(conn)
    paths = AppPaths.from_database(str(db))
    review = paths.intelligence_dir / "reviews" / "daily-2026-10-20.json"
    review.parent.mkdir(parents=True)
    review.write_text(json.dumps({
        "status": "ready",
        "captured_at": "2026-10-20 23:01:00",
        "evidence_fingerprint": "old",
    }), encoding="utf-8")

    assert "旧数据" in exporter._intelligence_report_status(
        str(db), "daily", "2026-10-20"
    )
    conn.close()


def test_report_status_keeps_ready_summary_when_fingerprint_read_fails(tmp_path, monkeypatch):
    from daylens.services import report_evidence_service

    db = tmp_path / "usage.db"
    conn = database.init_db(str(db))
    _insert(conn)
    paths = AppPaths.from_database(str(db))
    review = paths.intelligence_dir / "reviews" / "daily-2026-10-20.json"
    review.parent.mkdir(parents=True)
    review.write_text(json.dumps({
        "status": "ready",
        "captured_at": "2026-10-20 23:01:00",
        "evidence_fingerprint": "stored",
    }), encoding="utf-8")
    monkeypatch.setattr(
        report_evidence_service,
        "evidence_fingerprint",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(sqlite3.Error("locked")),
    )

    assert exporter._intelligence_report_status(
        str(db), "daily", "2026-10-20"
    ) == "已生成于 2026-10-20 23:01:00"
    conn.close()


def test_activity_ratio_delta_compares_percentage_points():
    assert exporter._activity_ratio_delta_text(60, 50) == "+10 个百分点"
    assert exporter._activity_ratio_delta_text(40, 50) == "-10 个百分点"
    assert exporter._activity_ratio_delta_text(50, None) == "无可比数据"


def test_report_dates_use_exact_daily_weekly_and_monthly_periods():
    assert report_dates("daily", date(2026, 10, 20)) == ["2026-10-20"]
    assert report_dates("weekly", date(2026, 10, 25)) == [
        f"2026-10-{day:02d}" for day in range(19, 26)
    ]
    assert report_dates("monthly", date(2026, 10, 31))[0] == "2026-10-01"
    assert report_dates("monthly", date(2026, 10, 31))[-1] == "2026-10-31"
