from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QItemSelectionModel, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QMessageBox,
    QTableWidget,
)

from daylens.gui.pages.reports import ReportsPage
from daylens.services import reports_service


def _app() -> QApplication:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    return QApplication.instance() or QApplication([])


def _create_report(reports_dir: Path, subdir: str, filename: str, content: str = "# 报告") -> Path:
    path = reports_dir / subdir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _select_rows(table: QTableWidget, rows: list[int]) -> None:
    selection_model = table.selectionModel()
    for row in rows:
        index = table.model().index(row, 0)
        selection_model.select(
            index,
            QItemSelectionModel.Select | QItemSelectionModel.Rows,
        )


def test_reports_page_starts_with_disabled_selection_actions(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    _create_report(reports_dir, "daily", "2026-06-24.md")

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.resize(1200, 680)
    page.show()
    app.processEvents()

    assert page.selected_report is None
    assert not page.btn_download.isEnabled()
    assert not page.btn_open.isEnabled()
    assert not page.btn_sync_selected.isEnabled()
    assert "选择一份报告" in page.detail_title.text()


def test_selecting_report_updates_detail_panel_and_actions(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    report_path = _create_report(reports_dir, "daily", "2026-06-24.md")

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.resize(1200, 680)
    page.show()
    app.processEvents()

    page.tab_daily.selectRow(0)
    app.processEvents()

    assert page.selected_report is not None
    assert page.selected_report["file_path"] == str(report_path)
    assert page.detail_title.text() == "2026-06-24"
    assert "日报" in page.detail_meta.text()
    assert page.btn_download.isEnabled()
    assert page.btn_open.isEnabled()
    assert page.btn_sync_selected.isEnabled()


def test_switching_report_type_clears_previous_selection(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    _create_report(reports_dir, "daily", "2026-06-24.md")
    _create_report(reports_dir, "weekly", "2026-06-22_2026-06-28_weekly.md")

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.show()
    app.processEvents()

    page.tab_daily.selectRow(0)
    app.processEvents()
    assert page.selected_report is not None

    page.tabs.setCurrentWidget(page.tab_weekly)
    app.processEvents()

    assert page.selected_report is None
    assert not page.btn_download.isEnabled()
    assert "选择一份报告" in page.detail_title.text()


def test_download_uses_selected_report_and_save_path(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    source = _create_report(reports_dir, "daily", "2026-06-24.md", "# 原始日报")
    destination = tmp_path / "downloaded" / "日报.md"
    calls = []

    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (str(destination), "Markdown 文件 (*.md)"),
    )
    monkeypatch.setattr(
        reports_service,
        "download_report",
        lambda source_path, destination_path: calls.append((source_path, destination_path))
        or destination_path,
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.show()
    app.processEvents()
    page.tab_daily.selectRow(0)
    app.processEvents()

    page.btn_download.click()

    assert calls == [(str(source), str(destination))]


def test_double_click_and_sync_use_selected_report(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    source = _create_report(reports_dir, "daily", "2026-06-24.md")
    opened = []
    synced = []

    monkeypatch.setattr(reports_service, "open_report", lambda path: opened.append(path))
    monkeypatch.setattr(
        reports_service,
        "sync_report_to_obsidian",
        lambda path, obsidian_path: synced.append((path, obsidian_path)),
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    app = _app()
    page = ReportsPage(
        str(tmp_path / "usage.db"),
        str(reports_dir),
        str(tmp_path / "vault"),
    )
    page.show()
    app.processEvents()

    page.tab_daily.selectRow(0)
    app.processEvents()
    item = page.tab_daily.item(0, 0)
    page.tab_daily.itemDoubleClicked.emit(item)
    page.btn_sync_selected.click()

    assert opened == [str(source)]
    assert synced == [(str(source), str(tmp_path / "vault"))]
    assert item.data(Qt.UserRole)["file_path"] == str(source)


def test_selecting_multiple_reports_updates_batch_state(tmp_path: Path):
    reports_dir = tmp_path / "reports"
    first = _create_report(reports_dir, "daily", "2026-06-24.md")
    second = _create_report(reports_dir, "daily", "2026-06-23.md")

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.show()
    app.processEvents()

    assert page.tab_daily.selectionMode() == QAbstractItemView.ExtendedSelection
    _select_rows(page.tab_daily, [0, 1])
    app.processEvents()

    selected_paths = {report["file_path"] for report in page.selected_reports}
    assert selected_paths == {str(first), str(second)}
    assert page.detail_title.text() == "已选择 2 份报告"
    assert page.btn_download.text() == "批量下载（2）"
    assert page.btn_download.isEnabled()
    assert not page.btn_open.isEnabled()
    assert not page.btn_sync_selected.isEnabled()


def test_batch_download_uses_selected_paths_and_target_directory(tmp_path: Path, monkeypatch):
    reports_dir = tmp_path / "reports"
    first = _create_report(reports_dir, "daily", "2026-06-24.md")
    second = _create_report(reports_dir, "daily", "2026-06-23.md")
    destination = tmp_path / "downloads"
    calls = []

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        lambda *args, **kwargs: str(destination),
    )
    monkeypatch.setattr(
        reports_service,
        "download_reports",
        lambda source_paths, destination_dir: calls.append((source_paths, destination_dir))
        or {
            "success_count": 2,
            "renamed_count": 0,
            "failure_count": 0,
            "saved_paths": [],
            "failures": [],
            "destination_dir": destination_dir,
        },
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)

    app = _app()
    page = ReportsPage(str(tmp_path / "usage.db"), str(reports_dir))
    page.show()
    app.processEvents()
    _select_rows(page.tab_daily, [0, 1])
    app.processEvents()

    page.btn_download.click()

    assert len(calls) == 1
    assert set(calls[0][0]) == {str(first), str(second)}
    assert calls[0][1] == str(destination)
