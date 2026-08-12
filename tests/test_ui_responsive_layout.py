from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QBoxLayout
import yaml

from daylens import database
from daylens.gui.main_window import MainWindow
from daylens.gui.widgets.elided_label import ElidedLabel


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
    assert window.dashboard_refresh.shutdown(timeout_ms=1_000) is True
    return app, window


def test_main_window_allows_resize_and_sidebar_scroll(tmp_path):
    app, window = _window(tmp_path)

    assert window.minimumSize().width() <= 1100
    assert window.minimumSize().height() <= 700
    assert window.maximumSize().width() > 1100
    assert window.windowFlags() & Qt.WindowMaximizeButtonHint
    assert window.nav_list.verticalScrollBarPolicy() == Qt.ScrollBarAsNeeded

    window.resize(1100, 700)
    app.processEvents()
    assert window.size().width() == 1100
    assert window.size().height() == 700
    window.dashboard_refresh.shutdown(timeout_ms=1_000)
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
    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    window.deleteLater()


def test_top_summary_reflows_from_four_columns_to_two_by_two(tmp_path):
    app, window = _window(tmp_path)

    window.resize(1600, 900)
    app.processEvents()
    wide_rows = {item.geometry().top() for item in window.summary_capsule_items}
    assert len(wide_rows) == 1
    assert window._top_action_layout.direction() == QBoxLayout.LeftToRight

    window.resize(1100, 700)
    app.processEvents()
    compact_rows = {item.geometry().top() for item in window.summary_capsule_items}
    compact_columns = {item.geometry().left() for item in window.summary_capsule_items}
    assert len(compact_rows) == 2
    assert len(compact_columns) == 2
    assert window._top_action_layout.direction() == QBoxLayout.TopToBottom

    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    window.deleteLater()


def test_initial_window_is_bounded_by_available_screen(tmp_path):
    app, window = _window(tmp_path)
    available = window.screen().availableGeometry()
    max_initial_width = max(window.minimumWidth(), int(available.width() * 0.95))
    max_initial_height = max(window.minimumHeight(), int(available.height() * 0.95))

    assert window.width() <= max_initial_width
    assert window.height() <= max_initial_height

    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    window.deleteLater()


def test_page_hint_uses_font_aware_elision_with_full_tooltip(tmp_path):
    app, window = _window(tmp_path)
    full_hint = (
        "第一行很长很长的诗句需要根据字体宽度省略\n"
        "第二行同样很长并保留完整作者信息"
    )
    window.lbl_page_hint.setText(full_hint)
    window.resize(1100, 700)
    app.processEvents()

    assert isinstance(window.lbl_page_hint, ElidedLabel)
    assert window.lbl_page_hint.toolTip() == full_hint

    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    window.deleteLater()


def test_trusted_insight_card_stays_compact_above_trend_at_1280x720(tmp_path):
    app, window = _window(tmp_path)
    window.resize(1280, 720)
    app.processEvents()

    page = window.pages["today"]
    assert window.page_scroll.horizontalScrollBar().maximum() == 0
    assert page.insight_card.height() <= 124
    assert page.insight_card.geometry().bottom() <= page.trend_card.geometry().top()
    assert page.trend_card.height() >= page.trend_card.minimumHeight()
    assert page.trend_card.width() >= 350
    assert page.trend_card._conclusion_label.geometry().bottom() < page.trend_card.canvas.geometry().top()
    metric_cells = [labels[0].parentWidget() for labels in page.trend_card._metric_labels]
    assert all(cell.geometry().bottom() <= page.trend_card.rect().bottom() for cell in metric_cells)
    assert all(label.textFormat() == Qt.PlainText for label in page.trend_card._dynamic_labels())
    assert page.insight_card.title_label.textFormat() == Qt.PlainText
    assert page.insight_card.evidence_label.wordWrap() is True

    window.dashboard_refresh.shutdown(timeout_ms=1_000)
    window.deleteLater()
