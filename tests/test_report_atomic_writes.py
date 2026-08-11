from __future__ import annotations

from pathlib import Path

import pytest

from daylens import exporter


def test_atomic_report_write_keeps_previous_file_when_replace_fails(
    tmp_path: Path,
    monkeypatch,
):
    report = tmp_path / "daily.md"
    report.write_text("previous report", encoding="utf-8")
    monkeypatch.setattr(
        exporter.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        exporter._atomic_write_text(str(report), "new report")

    assert report.read_text(encoding="utf-8") == "previous report"
    assert list(tmp_path.glob(".daily.md.*.tmp")) == []


def test_csv_export_keeps_previous_file_when_atomic_replace_fails(
    tmp_path: Path,
    monkeypatch,
):
    db_path = tmp_path / "usage.db"
    exporter.database.close_db(exporter.database.init_db(str(db_path)))
    output_dir = tmp_path / "reports"
    target = Path(exporter.daily_report_path(str(output_dir), "2026-08-10")).with_suffix(
        ".csv"
    )
    target.parent.mkdir(parents=True)
    target.write_bytes(b"previous csv")
    monkeypatch.setattr(
        exporter.os,
        "replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(OSError, match="replace failed"):
        exporter.export_csv(str(db_path), "2026-08-10", str(output_dir))

    assert target.read_bytes() == b"previous csv"
    assert list(target.parent.glob(".2026-08-10.csv.*.tmp")) == []
