import importlib


def test_report_backfill_worker_emits_service_result(monkeypatch):
    module = importlib.import_module("daylens.gui.report_backfill_worker")
    expected = {"generated_count": 2, "failure_count": 0}
    monkeypatch.setattr(
        module,
        "backfill_missing_daily_reports",
        lambda *_args: expected,
    )
    completed = []
    worker = module.ReportBackfillWorker(
        "usage.db",
        "reports",
        "E:/vault",
    )
    worker.completed.connect(completed.append)

    worker.run()

    assert completed == [expected]
