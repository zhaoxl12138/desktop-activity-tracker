from datetime import datetime

from daylens import exporter


def test_daily_metadata_before_cutoff_is_truthful_and_names_final_cutoff(monkeypatch):
    monkeypatch.setattr(exporter, "_report_data_updated_at", lambda *_: "2026-10-20 22:58:03")
    monkeypatch.setattr(exporter, "_intelligence_report_status", lambda *_: "待生成")

    lines = exporter._report_metadata_lines(
        "unused.db",
        "daily",
        ["2026-10-20"],
        generated_at=datetime(2026, 10, 20, 22, 59, 0),
    )

    assert "> 统计范围：2026-10-20（截至 22:59；23:00 形成当日定稿）" in lines
    assert "> 数据更新：2026-10-20 22:58:03" in lines
    assert "> 原生报告生成：2026-10-20 22:59:00" in lines
    assert "> 智能汇总：待生成" in lines


def test_completed_daily_and_periodic_metadata_show_exact_range(monkeypatch):
    monkeypatch.setattr(exporter, "_report_data_updated_at", lambda *_: "2026-10-19 23:00:00")
    monkeypatch.setattr(exporter, "_intelligence_report_status", lambda *_: "已生成于 2026-10-20 00:01:00")

    daily = exporter._report_metadata_lines(
        "unused.db", "daily", ["2026-10-19"],
        generated_at=datetime(2026, 10, 20, 8, 0),
    )
    weekly = exporter._report_metadata_lines(
        "unused.db", "weekly", ["2026-10-12", "2026-10-18"],
        generated_at=datetime(2026, 10, 20, 8, 0),
    )

    assert "> 统计范围：2026-10-19（截至 23:00）" in daily
    assert "> 统计范围：2026-10-12 ～ 2026-10-18" in weekly
    assert "> 智能汇总：已生成于 2026-10-20 00:01:00" in weekly
