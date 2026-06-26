from __future__ import annotations

from pathlib import Path

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
