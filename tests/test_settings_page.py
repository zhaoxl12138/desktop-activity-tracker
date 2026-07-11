from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from daylens.gui.pages.settings import SettingsPage
from daylens.services import settings_service


class DummyWorker:
    def __init__(self):
        self.settings_updated = False

    def update_settings(self, _config):
        self.settings_updated = True


def _build_page(tmp_path, monkeypatch):
    old_db = tmp_path / "usage.db"
    config = {
        "db_path": str(old_db),
        "obsidian_output_path": "",
        "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
    }
    monkeypatch.setattr(settings_service, "load_page_config", lambda *_: dict(config))
    monkeypatch.setattr(
        settings_service,
        "save_page_config",
        lambda **kwargs: {**config, "db_path": kwargs["new_db_path"]},
    )
    monkeypatch.setattr(QMessageBox, "information", lambda *args, **kwargs: None)
    app = QApplication.instance() or QApplication([])
    worker = DummyWorker()
    page = SettingsPage(
        str(tmp_path / "config.yaml"),
        str(old_db),
        str(tmp_path / "reports"),
        worker,
    )
    monkeypatch.setattr(page, "_toggle_startup", lambda enabled: bool(enabled))
    return app, page, worker, old_db


def test_database_path_change_requests_restart_instead_of_hot_reload(tmp_path, monkeypatch):
    app, page, worker, _old_db = _build_page(tmp_path, monkeypatch)
    emissions = []
    page.restart_requested.connect(lambda: emissions.append(True))
    page.edit_db.setText(str(tmp_path / "new.db"))

    page._save_all()
    app.processEvents()

    assert emissions == [True]
    assert worker.settings_updated is False
    page.deleteLater()


def test_equivalent_database_path_keeps_hot_reload(tmp_path, monkeypatch):
    app, page, worker, old_db = _build_page(tmp_path, monkeypatch)
    emissions = []
    page.restart_requested.connect(lambda: emissions.append(True))
    page.edit_db.setText(str(old_db))

    page._save_all()
    app.processEvents()

    assert emissions == []
    assert worker.settings_updated is True
    page.deleteLater()


def test_database_browser_selects_a_db_file(tmp_path, monkeypatch):
    _app, page, _worker, _old_db = _build_page(tmp_path, monkeypatch)
    selected = str(tmp_path / "selected.db")
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *args, **kwargs: (selected, "SQLite 数据库 (*.db)"),
    )

    page._browse_database()

    assert page.edit_db.text() == selected
    page.deleteLater()


def test_failed_startup_shortcut_is_saved_as_disabled(tmp_path, monkeypatch):
    _app, page, _worker, _old_db = _build_page(tmp_path, monkeypatch)
    captured = {}

    def fake_save(**kwargs):
        captured.update(kwargs)
        return {"db_path": kwargs["new_db_path"], "obsidian_output_path": ""}

    monkeypatch.setattr(settings_service, "save_page_config", fake_save)
    monkeypatch.setattr(page, "_toggle_startup", lambda _enabled: False)
    page.chk_startup.setChecked(True)

    page._save_all()

    assert captured["startup_enabled"] is False
    assert page.chk_startup.isChecked() is False
    page.deleteLater()
