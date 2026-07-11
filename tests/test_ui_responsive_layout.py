from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication
import yaml

from daylens import database
from daylens.gui.main_window import MainWindow


class DummyWorker(QObject):
    sample_updated = Signal(dict)

    def is_paused(self):
        return False

    def pause(self):
        pass

    def resume(self):
        pass

    def update_settings(self, _config):
        pass

    def stop(self):
        pass

    def wait(self, _timeout=0):
        return True


def _window(tmp_path):
    app = QApplication.instance() or QApplication([])
    db_path = tmp_path / "usage.db"
    database.close_db(database.init_db(str(db_path)))
    config = {
        "theme": "dark",
        "db_path": str(db_path),
        "obsidian_output_path": "",
        "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
        "categories": {},
    }
    (tmp_path / "config.yaml").write_text(yaml.safe_dump(config), encoding="utf-8")
    window = MainWindow(
        str(tmp_path), config, str(db_path), str(tmp_path / "config.yaml"),
        str(tmp_path / "reports"), DummyWorker(),
    )
    window.show()
    app.processEvents()
    return app, window


def test_main_window_allows_resize_and_sidebar_scroll(tmp_path):
    app, window = _window(tmp_path)

    assert window.minimumSize().width() <= 1100
    assert window.minimumSize().height() <= 700
    assert window.maximumSize().width() > 1100
    assert window.nav_list.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    window.resize(1100, 700)
    app.processEvents()
    assert window.size().width() == 1100
    assert window.size().height() == 700
    window.deleteLater()


def test_page_host_stays_inside_window_at_small_size(tmp_path):
    app, window = _window(tmp_path)
    window.resize(1100, 700)
    app.processEvents()

    host_rect = window.stack.parentWidget().geometry()
    assert host_rect.left() >= 0
    assert host_rect.top() >= 0
    assert host_rect.right() <= window.centralWidget().rect().right()
    assert host_rect.bottom() <= window.centralWidget().rect().bottom()
    window.deleteLater()
