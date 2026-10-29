from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication, QCheckBox, QPushButton

from daylens import database, exporter
from daylens.gui.pages.reports import ReportsPage
from daylens.gui.widgets.intelligence_settings import IntelligenceSettings
from daylens.services.intelligence_state import load_settings, save_settings
from daylens.session_tracker import ActivitySession


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _legacy_enabled(directory: Path) -> None:
    settings = load_settings(directory)
    save_settings(directory, {**settings, "behavior_analysis_enabled": True})


def _insert_trusted_session(db_path: Path, day: str) -> None:
    connection = database.init_db(str(db_path))
    start = datetime.fromisoformat(f"{day} 09:00:00")
    database.insert_session(
        connection,
        ActivitySession(
            session_id=f"retirement-{day}",
            start_time=start,
            end_time=start + timedelta(minutes=10),
            date=day,
            process_name="code.exe",
            exe_path="C:/code.exe",
            window_title="编辑项目",
            normalized_title="编辑项目",
            category_key="coding",
            category_name="编程开发",
            active_rule="interactive_required",
            duration_seconds=600,
            effective_seconds=600,
            engaged_seconds=600,
            passive_seconds=0,
            idle_seconds=0,
            metric_version="attention-v1",
            classification_version="rules-v1",
        ),
    )
    database.close_db(connection)


def test_reports_page_has_no_behavior_profile_entry(tmp_path: Path) -> None:
    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(tmp_path / "reports"))
    try:
        button_texts = [button.text() for button in page.findChildren(QPushButton)]
        assert "行为画像" not in button_texts
        assert not hasattr(page, "btn_behavior")
        assert not hasattr(page, "_show_behavior")
    finally:
        page.close()
        app.processEvents()


def test_settings_hide_behavior_switch_and_preserve_legacy_value(tmp_path: Path) -> None:
    _legacy_enabled(tmp_path)
    app = _app()
    widget = IntelligenceSettings(directory=tmp_path)
    try:
        checkbox_texts = [item.text() for item in widget.findChildren(QCheckBox)]
        assert not any("行为画像" in text for text in checkbox_texts)
        assert not hasattr(widget, "behavior")
        widget.classification.setChecked(False)
        widget._save()
        saved = load_settings(tmp_path)
        assert saved["behavior_analysis_enabled"] is True
        assert saved["classification_enabled"] is False
    finally:
        widget.close()
        app.processEvents()


@pytest.mark.parametrize("with_data", [False, True])
def test_native_reports_never_append_behavior_profile(
    tmp_path: Path, with_data: bool
) -> None:
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    intelligence_dir = tmp_path / "intelligence"
    _legacy_enabled(intelligence_dir)
    report_day = date.fromisocalendar(2026, 44, 3)
    if with_data:
        _insert_trusted_session(db_path, report_day.isoformat())

    output_dir = tmp_path / ("reports-with-data" if with_data else "reports-empty")
    paths = [
        exporter.export_markdown(str(db_path), report_day.isoformat(), str(output_dir)),
        exporter.export_weekly_report(
            str(db_path), report_day.isocalendar().year,
            report_day.isocalendar().week, str(output_dir)
        ),
        exporter.export_monthly_report(
            str(db_path), report_day.year, report_day.month, str(output_dir)
        ),
    ]

    for report_path in paths:
        text = Path(report_path).read_text(encoding="utf-8")
        assert "行为画像" not in text
        assert "暂不生成画像和趋势" not in text


def test_retired_behavior_modules_are_removed() -> None:
    root = Path(__file__).resolve().parents[1]
    assert not (root / "src/daylens/services/behavior_profile_service.py").exists()
    assert not (root / "src/daylens/services/behavior_experiment_service.py").exists()
    assert not (root / "src/daylens/gui/widgets/behavior_dialog.py").exists()
