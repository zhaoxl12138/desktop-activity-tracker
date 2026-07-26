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
