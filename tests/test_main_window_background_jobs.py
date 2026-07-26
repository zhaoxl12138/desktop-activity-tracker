from __future__ import annotations

from types import SimpleNamespace


class _FakeQueue:
    def __init__(self):
        self.submissions = []

    def submit(self, key, task):
        self.submissions.append((key, task))
        return True


def _window():
    return SimpleNamespace(
        background_tasks=_FakeQueue(),
        db_path="usage.db",
        reports_dir="reports",
        _live_obsidian_path=lambda: "D:/Notes",
        _last_report_gen=0,
    )


def test_quick_report_is_submitted_to_background_queue(monkeypatch):
    from daylens.gui import main_window

    window = _window()
    monkeypatch.setattr(
        main_window,
        "execute_report_job",
        lambda *_args: (_ for _ in ()).throw(AssertionError("GUI thread export")),
    )

    main_window.MainWindow._quick_report(window)

    assert [key for key, _task in window.background_tasks.submissions] == [
        "report:quick"
    ]


def test_scheduled_reports_are_submitted_to_background_queue(monkeypatch):
    from daylens.gui import main_window

    window = _window()
    monkeypatch.setattr(main_window.time, "time", lambda: 1_000)
    monkeypatch.setattr(
        main_window,
        "execute_report_job",
        lambda *_args: (_ for _ in ()).throw(AssertionError("GUI thread export")),
    )

    main_window.MainWindow._check_report_schedule(window)
    main_window.MainWindow._auto_generate_daily_report(window)
    main_window.MainWindow._start_report_backfill(window)

    assert [key for key, _task in window.background_tasks.submissions] == [
        "report:periodic",
        "report:daily",
        "report:backfill",
    ]
