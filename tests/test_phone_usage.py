from datetime import date

from daylens.services.phone_usage import (
    available_phone_days, find_phone_archive, load_phone_usage, sync_phone_archive,
)


def _write_day(archive, day, received_at, body):
    path = archive / day[:4] / day[:7] / f"{day}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\ndate: {day}\nreceived_at: {received_at}\n---\n\n## App 使用时长\n\n{body}\n",
        encoding="utf-8",
    )


def test_phone_usage_ranks_received_days_across_month_boundary(tmp_path):
    reports = tmp_path / "时间追踪" / "桌面活动日报" / "2026" / "2026-12"
    archive = find_phone_archive(str(reports))
    assert archive == tmp_path / "时间追踪" / "手机屏幕使用时间"
    _write_day(archive, "2026-11-30", "2026-12-01T00:00:05+08:00",
               "    App A (35分钟)\n    App B（1小時 2分鐘 3秒）")
    _write_day(archive, "2026-12-01", "2026-12-01T21:00:00+08:00",
               "    app a (40分钟)\n    App A (20分钟)\n    App (Beta) (5秒)")
    _write_day(archive, "2026-12-02", "2026-12-03T00:00:00+08:00", "    malformed")
    _write_day(archive, "2026-12-04", "2026-12-05T00:00:00+08:00", "    App B (1小时)")

    usage = load_phone_usage(archive, date(2026, 11, 27), date(2026, 12, 3))

    assert usage.received_days == 2
    assert usage.snapshot_days == 1
    assert usage.unreadable_days == 1
    assert usage.apps == [("App A", 4500), ("App B", 3723), ("App (Beta)", 5)]
    assert available_phone_days(archive, through=date(2026, 12, 3)) == [
        date(2026, 12, 1), date(2026, 11, 30),
    ]


def test_phone_usage_does_not_treat_missing_days_as_zero(tmp_path):
    usage = load_phone_usage(tmp_path, date(2026, 11, 25), date(2026, 11, 25))
    assert usage.apps == []
    assert usage.received_days == 0
    assert usage.unreadable_days == 0


def test_sync_phone_archive_copies_updates_and_keeps_local_history(tmp_path):
    source, local = tmp_path / "Daylog", tmp_path / "DayLens"
    day = date(2026, 11, 26)
    _write_day(source, "2026-11-25", "2026-11-26T00:00:05+08:00", "    App A (35分钟)")
    _write_day(source, day.isoformat(), "2026-11-27T00:00:05+08:00", "    App B (1小时)")
    _write_day(source, "2026-11-27", "2026-11-28T00:00:05+08:00", "    malformed")
    assert sync_phone_archive(source, local, through=date(2026, 11, 27)) == 2
    assert sync_phone_archive(source, local, through=date(2026, 11, 27)) == 0

    _write_day(source, day.isoformat(), "2026-11-26T20:00:00+08:00", "    App B (10分钟)")
    assert sync_phone_archive(source, local, through=day) == 0

    _write_day(source, day.isoformat(), "2026-11-27T01:00:00+08:00", "    App B (2小时)")
    assert sync_phone_archive(source, local, through=day) == 1
    file = "2026/2026-11/2026-11-26.md"
    assert (local / file).read_bytes() == (source / file).read_bytes()

    source.rename(tmp_path / "offline")
    assert sync_phone_archive(source, local, through=day) == 0
    assert available_phone_days(local, through=day) == [day, date(2026, 11, 25)]
    assert load_phone_usage(local, day, day).apps == [("App B", 7200)]
