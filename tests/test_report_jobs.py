from __future__ import annotations


def test_periodic_report_job_generates_and_syncs_in_worker_context(
    tmp_path,
    monkeypatch,
):
    from daylens.services import reports_service
    from daylens.services.reports_service import ReportJob, execute_report_job

    generated = [str(tmp_path / "weekly.md"), str(tmp_path / "monthly.md")]
    synced = []
    monkeypatch.setattr(
        reports_service,
        "auto_generate_current_reports",
        lambda *_args, **_kwargs: generated,
    )
    monkeypatch.setattr(
        reports_service,
        "sync_report_to_obsidian",
        lambda path, destination: synced.append((path, destination)),
    )
    job = ReportJob(
        kind="periodic",
        db_path="usage.db",
        reports_dir=str(tmp_path),
        obsidian_path="D:/Notes",
    )

    result = execute_report_job(job)

    assert job.key == "report:periodic"
    assert result == {
        "kind": "periodic",
        "generated_paths": generated,
    }
    assert synced == [
        (generated[0], "D:/Notes"),
        (generated[1], "D:/Notes"),
    ]


def test_quick_report_job_returns_manual_export_result(tmp_path, monkeypatch):
    from daylens.services import shell_service
    from daylens.services.reports_service import ReportJob, execute_report_job

    report_path = str(tmp_path / "daily" / "today.md")
    monkeypatch.setattr(
        shell_service,
        "generate_daily_report",
        lambda *args: (report_path, "D:/Notes/today.md"),
    )

    result = execute_report_job(
        ReportJob(
            kind="quick",
            db_path="usage.db",
            reports_dir=str(tmp_path),
            obsidian_path="D:/Notes",
        )
    )

    assert result == {
        "kind": "quick",
        "generated_paths": [report_path],
        "synced_path": "D:/Notes/today.md",
    }


def test_hourly_daily_report_job_syncs_latest_report(tmp_path, monkeypatch):
    from daylens.services import reports_service
    from daylens.services.reports_service import ReportJob, execute_report_job

    report_path = str(tmp_path / "daily" / "today.md")
    synced = []
    monkeypatch.setattr(
        reports_service,
        "auto_generate_daily_report",
        lambda *_args: report_path,
    )
    monkeypatch.setattr(
        reports_service,
        "sync_report_to_obsidian",
        lambda path, destination: synced.append((path, destination)),
    )

    result = execute_report_job(
        ReportJob(
            kind="daily",
            db_path="usage.db",
            reports_dir=str(tmp_path),
            obsidian_path="D:/Notes",
        )
    )

    assert result == {
        "kind": "daily",
        "generated_paths": [report_path],
    }
    assert synced == [(report_path, "D:/Notes")]


def test_backfill_report_job_returns_reconciliation_summary(
    tmp_path,
    monkeypatch,
):
    from daylens.services import reports_service
    from daylens.services.reports_service import ReportJob, execute_report_job

    summary = {
        "generated_count": 2,
        "failure_count": 0,
        "generated_paths": ["one.md", "two.md"],
    }
    monkeypatch.setattr(
        reports_service,
        "backfill_missing_daily_reports",
        lambda *_args: summary,
    )

    result = execute_report_job(
        ReportJob(
            kind="backfill",
            db_path="usage.db",
            reports_dir=str(tmp_path),
            obsidian_path="D:/Notes",
        )
    )

    assert result == {
        "kind": "backfill",
        "summary": summary,
    }
