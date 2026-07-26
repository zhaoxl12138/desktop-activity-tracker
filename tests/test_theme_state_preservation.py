from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import yaml
from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from daylens import database
from daylens.gui.main_window import MainWindow


class Worker(QObject):
    sample_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self.pause_calls = 0
        self.resume_calls = 0

    def is_paused(self):
        return False

    def pause(self):
        self.pause_calls += 1

    def resume(self):
        self.resume_calls += 1

    def update_settings(self, _config):
        pass

    def stop(self):
        pass

    def wait(self, _timeout=0):
        return True


def test_theme_switch_preserves_pages_navigation_and_unsaved_rule_state(
    tmp_path, monkeypatch
):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.init_db(str(db_path)).close()
    config = {
        "theme": "dark",
        "db_path": str(db_path),
        "obsidian_output_path": "",
        "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
        "categories": {
            "coding": {
                "display_name": "Coding",
                "active_rule": "interactive_required",
                "match": {
                    "process_names": ["Code.exe"],
                    "title_keywords": [],
                },
            },
            "other": {
                "display_name": "Other",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        },
    }
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(config, allow_unicode=True),
        encoding="utf-8",
    )
    worker = Worker()
    monkeypatch.setattr(
        "daylens.utils.save_user_config",
        lambda *_args, **_kwargs: None,
    )
    window = MainWindow(
        str(tmp_path),
        config,
        str(db_path),
        str(config_path),
        str(tmp_path / "reports"),
        worker,
    )
    window.show()
    window.nav_list.setCurrentRow(5)
    app.processEvents()
    rules_page = window.pages["rules"]
    original_pages = dict(window.pages)
    rules_page.edit_name.setText("Unsaved theme state")
    assert rules_page._dirty is True

    window._toggle_theme(False)
    app.processEvents()

    assert window.current_theme == "light"
    assert window._current_nav_key == "rules"
    assert window.nav_list.currentRow() == 5
    assert all(window.pages[key] is page for key, page in original_pages.items())
    assert window.pages["rules"].edit_name.text() == "Unsaved theme state"
    assert window.pages["rules"]._dirty is True
    assert worker.pause_calls == 0
    assert worker.resume_calls == 0
    window.deleteLater()
