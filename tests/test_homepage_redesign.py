from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import yaml
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication, QLabel, QVBoxLayout

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from desktop_activity_tracker import database  # noqa: E402
from desktop_activity_tracker.gui.main_window import MainWindow, NAV_ITEMS  # noqa: E402
from desktop_activity_tracker.gui import style as ui_style  # noqa: E402


class DummyWorker(QObject):
    sample_updated = Signal(dict)

    def __init__(self):
        super().__init__()
        self._paused = False

    def is_paused(self):
        return self._paused

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def update_settings(self, config):
        return None

    def stop(self):
        return None

    def wait(self, timeout=0):
        return True


def _write_config(path: Path):
    config = {
        "theme": "dark",
        "db_path": str(path.parent / "usage.db"),
        "reports_dir": str(path.parent / "reports"),
        "obsidian_output_path": "",
        "tracker": {
            "sample_interval_seconds": 1,
            "flush_interval_seconds": 5,
            "idle_threshold_seconds": 60,
            "min_session_seconds": 2,
        },
        "categories": {
            "coding": {
                "display_name": "编程开发",
                "active_rule": "interactive_required",
                "match": {"process_names": ["Code.exe"], "title_keywords": []},
            },
            "tools": {
                "display_name": "系统工具",
                "active_rule": "interactive_required",
                "match": {"process_names": ["DayLens.exe"], "title_keywords": []},
            },
            "other": {
                "display_name": "其他",
                "active_rule": "interactive_required",
                "match": {"process_names": [], "title_keywords": []},
            },
        },
    }
    path.write_text(yaml.safe_dump(config, allow_unicode=True), encoding="utf-8")
    return config


def _dashboard_snapshot(**overrides):
    today = datetime.now().date()
    payload = {
        "today": today.strftime("%Y-%m-%d"),
        "stats": {"totals": {}, "by_category": [], "by_app": [], "by_app_detail": []},
        "totals": {
            "effective_seconds": 0,
            "idle_seconds": 0,
            "total_seconds": 0,
            "active_ratio": 0,
        },
        "distribution_sections": [],
        "day_comparison": {
            key: {"direction": "empty", "delta_seconds": 0}
            for key in ("work", "entertainment", "social")
        },
        "sessions": [],
        "focus_summary": "今日暂未识别到连续专注时段。",
        "consecutive_days": 0,
        "top_app_rows": [],
        "trend": {
            "today": [0] * 24,
            "today_work": [0] * 24,
            "today_entertainment": [0] * 24,
            "yesterday": [0] * 24,
            "yesterday_work": [0] * 24,
            "yesterday_entertainment": [0] * 24,
            "seven_days": [[0] * 24 for _ in range(7)],
            "seven_day_labels": [
                (today - timedelta(days=offset)).strftime("%Y-%m-%d")
                for offset in reversed(range(7))
            ],
            "thirty_days": [0] * 30,
        },
    }
    payload.update(overrides)
    return payload


def test_homepage_shell_matches_reference_structure():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        config = _write_config(config_path)
        db_path = tmp_path / "usage.db"
        database.init_db(str(db_path)).close()

        app = QApplication.instance() or QApplication([])
        window = MainWindow(
            str(tmp_path),
            config,
            str(db_path),
            str(config_path),
            str(reports_dir),
            DummyWorker(),
        )
        window.show()
        app.processEvents()

        available = window.screen().availableGeometry()
        expected_width = min(
            1600,
            max(window.minimumWidth(), int(available.width() * 0.95)),
        )
        expected_height = min(
            900,
            max(window.minimumHeight(), int(available.height() * 0.95)),
        )
        assert window.size().width() == expected_width
        assert window.size().height() == expected_height
        assert window.minimumSize().width() == 1100
        assert window.minimumSize().height() == 700
        assert window.maximumSize().width() > 1100
        assert set(window.capsule_values) == {"total", "work", "ent", "social"}
        assert window.capsule_labels["total"].text() == "参与时长"
        assert window.capsule_labels["work"].text() == "工作学习"
        assert window.capsule_labels["ent"].text() == "娱乐休闲"
        assert window.capsule_icons["ent"].text() == "📺"
        assert window.capsule_labels["social"].text() == "社交通讯"
        assert all("活跃度" not in hint for _title, _key, hint in NAV_ITEMS)
        for item in window.summary_capsule_items:
            item_layout = item.layout()
            assert isinstance(item_layout, QVBoxLayout)
            assert item_layout.alignment() & Qt.AlignHCenter
            assert item.minimumWidth() >= 150
        assert window._summary_capsule_grid.horizontalSpacing() >= 24
        assert window._summary_capsule_grid.verticalSpacing() >= 10
        window.resize(1366, 768)
        app.processEvents()
        assert window._top_bar_compact is True
        assert not hasattr(window, "bottom_bar")
        assert window.pages["today"].metric_cards == {}
        assert getattr(window.pages["today"], "time_stats_ratio_ring", None) is None
        assert window.pages["today"].time_stats_card is None
        assert window.pages["today"].insight_card is None
        assert getattr(window.pages["today"], "insight_grid_widget", None) is None
        assert getattr(window.pages["today"], "insight_empty_label", None) is None
        assert window.pages["today"].trend_card.height() <= 300
        assert window.pages["today"].top_app_card.minimumHeight() >= 180
        assert window.pages["today"].daily_goals_card.minimumHeight() >= 130
        assert window.pages["today"].distribution_cmp_labels == {}
        distribution_texts = {
            label.text()
            for label in window.pages["today"].distribution_card.findChildren(QLabel)
        }
        assert "较昨日" not in distribution_texts
        assert ui_style.get_category_color("other") != ui_style.COLORS["social_purple"]
        assert window.pages["today"]._distribution_color("other") == ui_style.get_category_color("other")
        assert window.pages["today"]._color_for_category("other") == ui_style.get_category_color("other")
        assert window.pages["today"]._color_for_category("idle") == ui_style.COLORS["timeline_idle"]
        assert window.pages["today"]._color_for_category("idle_leave") == ui_style.COLORS["timeline_idle"]
        focus_legend_labels = window.pages["today"].focus_legend_labels
        assert [label.text() for label in focus_legend_labels] == [
            "工作参与",
            "未计入专注",
        ]
        focus_legend_widgets = [
            *window.pages["today"].focus_legend_dots,
            *focus_legend_labels,
        ]
        assert all(label.textFormat() == Qt.PlainText for label in focus_legend_widgets)
        assert all(
            label.geometry().right()
            <= window.pages["today"].focus_timeline_card.contentsRect().right()
            for label in focus_legend_widgets
        )
        assert window.pages["today"].focus_legend_colors == [
            ui_style.COLORS["coding_green"],
            ui_style.COLORS["timeline_idle"],
        ]
        episode_title = window.pages["today"].focus_timeline_card.findChild(
            QLabel,
            "workEpisodeSectionTitle",
        )
        assert episode_title is not None
        assert episode_title.textFormat() == Qt.PlainText
        assert "font-size: 15px" in episode_title.styleSheet()
        assert "font-weight: 800" in episode_title.styleSheet()
        assert ui_style.COLORS["primary_hover"] in episode_title.styleSheet()
        assert window.dashboard_refresh.timer.isActive() is True

        window.nav_list.setCurrentRow(1)
        app.processEvents()
        assert window.dashboard_refresh.timer.isActive() is True

        window.nav_list.setCurrentRow(0)
        app.processEvents()
        assert window.dashboard_refresh.timer.isActive() is True

        window.close()
        app.processEvents()
        assert window.dashboard_refresh.timer.isActive() is False
        assert window.dashboard_refresh.shutdown(timeout_ms=1_000) is True


def test_today_overview_applies_old_and_trusted_snapshots_safely():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config_path = tmp_path / "config.yaml"
        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        config = _write_config(config_path)
        db_path = tmp_path / "usage.db"
        database.init_db(str(db_path)).close()
        app = QApplication.instance() or QApplication([])
        window = MainWindow(
            str(tmp_path),
            config,
            str(db_path),
            str(config_path),
            str(reports_dir),
            DummyWorker(),
        )
        window.resize(1280, 720)
        window.show()
        app.processEvents()
        assert window.dashboard_refresh.shutdown(timeout_ms=1_000) is True
        page = window.pages["today"]

        page.apply_snapshot(_dashboard_snapshot())
        app.processEvents()

        assert page.active_status_label.text().startswith("有效 ")
        assert page.passive_status_label.text() == "被动媒体 --"
        assert page.donut_widget._primary_label == "有效时长"
        assert page.last_shell_primary_label == "有效时长"
        legacy_time_card = page._build_time_stats_card()
        legacy_time_labels = {
            label.text() for label in legacy_time_card.findChildren(QLabel)
        }
        assert "有效时长" in legacy_time_labels
        assert "有效时间占比" in legacy_time_labels
        assert not any("活跃" in text for text in legacy_time_labels)
        legacy_time_card.deleteLater()
        window._update_top_bar()
        assert window.capsule_labels["total"].text() == "有效时长"
        assert page.trust_badge.text() == "口径待稳定"
        assert page.trust_badge.isVisible() is True
        assert page.insight_card is None
        assert page.classification_notice.isVisible() is False

        trusted = _dashboard_snapshot(
            totals={
                "effective_seconds": 5_400,
                "engaged_seconds": 3_600,
                "passive_seconds": 1_800,
                "idle_seconds": 600,
                "total_seconds": 6_000,
                "active_ratio": 60,
                "passive_ratio": 30,
                "idle_ratio": 10,
                "primary_metric": "engaged",
            },
            trust={
                "level": "high",
                "reasons": [],
                "category_comparable": True,
            },
            comparison={
                "comparable": True,
                "category_comparable": True,
                "reason": "",
            },
            insight={
                "kind": "best_window",
                "title": "你的优势时段是 09:00–11:00",
                "evidence": "最近14天有7个工作日。",
                "action": "保护这个时间窗口。",
                "confidence": "high",
            },
            trend={
                **_dashboard_snapshot()["trend"],
                "thirty_days": [0.5] * 30,
                "thirty_day_metric": "engaged",
            },
        )
        page.apply_snapshot(trusted)
        app.processEvents()

        assert page.active_status_label.text() == "参与 60%"
        assert page.passive_status_label.text() == "被动媒体 30%"
        assert page.donut_widget._primary_seconds == 3_600
        assert page.donut_widget._primary_label == "参与时长"
        assert page.donut_widget._total_seconds == 6_000
        assert [segment[0] for segment in page.donut_widget._segments] == [
            "参与",
            "被动媒体",
            "挂机/空闲",
        ]
        assert page.last_shell_primary_seconds == 3_600
        assert page.last_shell_primary_label == "参与时长"
        window._update_top_bar()
        assert window.capsule_labels["total"].text() == "参与时长"
        assert window.capsule_values["total"].text() == "1时"
        page.trend_card.set_mode("30d")
        assert page.trend_card._status_label.text() == "数据积累中"
        assert page.trend_card._legend_text() == ""
        assert page.trust_badge.isVisible() is False
        assert page.insight_card is None
        assert page.classification_notice.isVisible() is False

        mixed = dict(trusted)
        mixed["trust"] = {
            "level": "medium",
            "reasons": ["范围内存在多个分类版本"],
            "category_comparable": False,
        }
        mixed["comparison"] = {
            "comparable": True,
            "category_comparable": False,
            "reason": "分类规则不一致，仅总参与时间可比",
        }
        mixed["insight"] = None
        mixed["day_comparison"] = {
            key: {"direction": "up", "delta_seconds": 600}
            for key in ("work", "entertainment", "social")
        }
        page.apply_snapshot(mixed)
        app.processEvents()

        assert page.trust_badge.isVisible() is True
        assert page.classification_notice.isVisible() is False
        assert page.distribution_cmp_labels == {}
        assert page.insight_card is None

        window.close()
        app.processEvents()
        assert window.dashboard_refresh.shutdown(timeout_ms=1_000) is True
