from __future__ import annotations

import sqlite3
from pathlib import Path

from daylens import database, exporter
from daylens.services import reports_service


def test_list_report_rows_returns_complete_report_metadata(tmp_path: Path):
    report_path = tmp_path / "daily" / "2026" / "2026-06" / "2026-06-24.md"
    report_path.parent.mkdir(parents=True)
    report_path.write_text("# 日报\n", encoding="utf-8")

    rows = reports_service.list_report_rows(str(tmp_path), "daily")

    assert len(rows) == 1
    assert rows[0]["label"] == "2026-06-24"
    assert rows[0]["filename"] == "2026-06-24.md"
    assert rows[0]["file_path"] == str(report_path)
    assert rows[0]["report_type"] == "日报"
    assert rows[0]["modified_text"]


def test_download_report_copies_selected_file_without_modifying_source(tmp_path: Path):
    source = tmp_path / "reports" / "daily" / "2026-06-24.md"
    source.parent.mkdir(parents=True)
    source.write_text("# DayLens 日报\n原始内容", encoding="utf-8")
    destination = tmp_path / "downloads" / "我的日报.md"

    result = reports_service.download_report(str(source), str(destination))

    assert result == str(destination)
    assert destination.read_text(encoding="utf-8") == "# DayLens 日报\n原始内容"
    assert source.read_text(encoding="utf-8") == "# DayLens 日报\n原始内容"


def test_download_report_rejects_missing_source(tmp_path: Path):
    missing = tmp_path / "missing.md"
    destination = tmp_path / "download.md"

    try:
        reports_service.download_report(str(missing), str(destination))
    except FileNotFoundError as exc:
        assert str(missing) in str(exc)
    else:
        raise AssertionError("missing source should raise FileNotFoundError")


def test_download_reports_copies_all_files_and_avoids_name_collisions(tmp_path: Path):
    first = tmp_path / "daily" / "2026-06-24.md"
    second = tmp_path / "weekly" / "2026-06-24.md"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    first.write_text("日报", encoding="utf-8")
    second.write_text("周报", encoding="utf-8")
    destination = tmp_path / "downloads"
    destination.mkdir()
    (destination / "2026-06-24.md").write_text("已有文件", encoding="utf-8")

    result = reports_service.download_reports(
        [str(first), str(second)],
        str(destination),
    )

    assert result["success_count"] == 2
    assert result["renamed_count"] == 2
    assert result["failure_count"] == 0
    assert (destination / "2026-06-24 (1).md").read_text(encoding="utf-8") == "日报"
    assert (destination / "2026-06-24 (2).md").read_text(encoding="utf-8") == "周报"


def test_download_reports_continues_after_missing_source(tmp_path: Path):
    source = tmp_path / "daily" / "2026-06-24.md"
    source.parent.mkdir(parents=True)
    source.write_text("日报", encoding="utf-8")
    missing = tmp_path / "daily" / "missing.md"
    destination = tmp_path / "downloads"

    result = reports_service.download_reports(
        [str(missing), str(source)],
        str(destination),
    )

    assert result["success_count"] == 1
    assert result["failure_count"] == 1
    assert len(result["failures"]) == 1
    assert result["failures"][0]["source_path"] == str(missing)


def test_auto_generate_refreshes_existing_current_reports(tmp_path: Path, monkeypatch):
    weekly = Path(reports_service.weekly_report_path(str(tmp_path)))
    monthly = Path(reports_service.monthly_report_path(str(tmp_path)))
    weekly.parent.mkdir(parents=True, exist_ok=True)
    monthly.parent.mkdir(parents=True, exist_ok=True)
    weekly.write_text("stale weekly", encoding="utf-8")
    monthly.write_text("stale monthly", encoding="utf-8")
    calls = []
    monkeypatch.setattr(
        reports_service,
        "generate_weekly_report",
        lambda *_: calls.append("weekly") or str(weekly),
    )
    monkeypatch.setattr(
        reports_service,
        "generate_monthly_report",
        lambda *_: calls.append("monthly") or str(monthly),
    )

    generated = reports_service.auto_generate_current_reports("usage.db", str(tmp_path))

    assert calls == ["weekly", "monthly"]
    assert generated == [str(weekly), str(monthly)]


def test_auto_generate_daily_report_refreshes_today(tmp_path: Path, monkeypatch):
    expected = tmp_path / "daily" / "2026-07-17.md"
    calls = []
    monkeypatch.setattr(
        reports_service,
        "generate_daily_report",
        lambda db_path, reports_dir: calls.append((db_path, reports_dir)) or str(expected),
    )

    result = reports_service.auto_generate_daily_report("usage.db", str(tmp_path))

    assert result == str(expected)
    assert calls == [("usage.db", str(tmp_path))]


def _create_database_with_dates(tmp_path: Path, dates: list[str]) -> Path:
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    conn = sqlite3.connect(db_path)
    conn.executemany(
        """
        INSERT INTO activity_sessions
            (session_id,start_time,end_time,date,duration_seconds,
             effective_seconds,idle_seconds)
        VALUES (?,?,?,?,?,?,?)
        """,
        [
            (
                f"session-{index}",
                f"{date_str} 10:00:00",
                f"{date_str} 10:01:00",
                date_str,
                60,
                60,
                0,
            )
            for index, date_str in enumerate(dates)
        ],
    )
    conn.commit()
    conn.close()
    return db_path


def test_backfill_generates_only_missing_historical_reports(tmp_path, monkeypatch):
    db_path = _create_database_with_dates(
        tmp_path,
        ["2026-07-20", "2026-07-21", "2026-07-24"],
    )
    reports_dir = tmp_path / "reports"
    existing = Path(
        exporter.daily_report_path(
            str(reports_dir / "daily"),
            "2026-07-20",
        )
    )
    existing.parent.mkdir(parents=True)
    existing.write_text("existing", encoding="utf-8")
    generated_dates = []

    def fake_export(_db, date_str, output_dir):
        generated_dates.append(date_str)
        path = Path(exporter.daily_report_path(output_dir, date_str))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(date_str, encoding="utf-8")
        return str(path)

    monkeypatch.setattr(reports_service.exporter, "export_markdown", fake_export)

    result = reports_service.backfill_missing_daily_reports(
        str(db_path),
        str(reports_dir),
        today_str="2026-07-24",
    )

    assert generated_dates == ["2026-07-21"]
    assert result["generated_count"] == 1
    assert result["skipped_count"] == 2


def test_backfill_continues_after_one_report_failure(tmp_path, monkeypatch):
    db_path = _create_database_with_dates(
        tmp_path,
        ["2026-07-20", "2026-07-21", "2026-07-22"],
    )

    def fake_export(_db, date_str, output_dir):
        if date_str == "2026-07-20":
            raise RuntimeError("broken day")
        path = Path(exporter.daily_report_path(output_dir, date_str))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(date_str, encoding="utf-8")
        return str(path)

    monkeypatch.setattr(reports_service.exporter, "export_markdown", fake_export)

    result = reports_service.backfill_missing_daily_reports(
        str(db_path),
        str(tmp_path / "reports"),
        today_str="2026-07-23",
    )

    assert result["generated_count"] == 2
    assert result["failure_count"] == 1
    assert result["failures"][0]["date"] == "2026-07-20"
