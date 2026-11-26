from __future__ import annotations

from datetime import datetime
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


def test_phone_archive_runs_once_after_0005_on_the_report_timer(monkeypatch):
    from daylens.gui import main_window

    now = datetime(2026, 11, 27, 0, 4)

    class Clock:
        @staticmethod
        def now():
            return now

    monkeypatch.setattr(main_window, "datetime", Clock)
    window = _window()
    window._phone_sync_day = None
    window.paths = SimpleNamespace(phone_archive="local")
    assert main_window.MainWindow._queue_phone_archive_sync(window)
    window._queue_phone_archive_sync = lambda: main_window.MainWindow._queue_phone_archive_sync(window)
    main_window.MainWindow._check_phone_archive_schedule(window)
    assert len(window.background_tasks.submissions) == 1

    now = now.replace(minute=5)
    main_window.MainWindow._check_phone_archive_schedule(window)
    main_window.MainWindow._check_phone_archive_schedule(window)
    assert len(window.background_tasks.submissions) == 2
    assert window._phone_sync_day == now.date()
