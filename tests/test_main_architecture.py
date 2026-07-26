from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN_SOURCE = (ROOT / "src" / "daylens" / "main.py").read_text(encoding="utf-8")
TODAY_OVERVIEW_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "today_overview.py").read_text(encoding="utf-8")
GITIGNORE_SOURCE = (ROOT / ".gitignore").read_text(encoding="utf-8")
SETTINGS_PAGE_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "settings.py").read_text(encoding="utf-8")
REPORTS_PAGE_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "reports.py").read_text(encoding="utf-8")
SOFTWARE_STATS_PAGE_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "software_stats.py").read_text(encoding="utf-8")
CATEGORY_STATS_PAGE_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "category_stats.py").read_text(encoding="utf-8")
RULE_CONFIG_PAGE_SOURCE = (ROOT / "src" / "daylens" / "gui" / "pages" / "rule_config.py").read_text(encoding="utf-8")
WIZARD_SOURCE = (ROOT / "src" / "daylens" / "gui" / "wizard.py").read_text(encoding="utf-8")
MAIN_WINDOW_SOURCE = (ROOT / "src" / "daylens" / "gui" / "main_window.py").read_text(encoding="utf-8")
TRAY_MANAGER_SOURCE = (ROOT / "src" / "daylens" / "gui" / "tray_manager.py").read_text(encoding="utf-8")
COMMAND_HANDLERS_SOURCE = (ROOT / "src" / "daylens" / "services" / "command_handlers.py").read_text(encoding="utf-8")
WORKER_SOURCE = (ROOT / "src" / "daylens" / "gui" / "worker.py").read_text(encoding="utf-8")
GUI_BOOTSTRAP_SOURCE = (ROOT / "src" / "daylens" / "services" / "gui_bootstrap.py").read_text(encoding="utf-8")
COMMAND_HANDLERS_SOURCE_PATH = ROOT / "src" / "daylens" / "services" / "command_handlers.py"
GUI_BOOTSTRAP_SOURCE_PATH = ROOT / "src" / "daylens" / "services" / "gui_bootstrap.py"


def test_main_delegates_parser_and_runtime_helpers():
    assert "from .cli import build_parser" in MAIN_SOURCE or "from daylens.cli import build_parser" in MAIN_SOURCE
    assert "from .runtime import" in MAIN_SOURCE or "from daylens.runtime import" in MAIN_SOURCE
    assert "def resolve_config_path" not in MAIN_SOURCE
    assert "def resolve_reports_dir" not in MAIN_SOURCE
    assert "def load_config" not in MAIN_SOURCE
    assert "launch_gui" in MAIN_SOURCE


def test_today_overview_avoids_direct_database_queries():
    assert "database.query_" not in TODAY_OVERVIEW_SOURCE
    assert "self.metric_cards" not in TODAY_OVERVIEW_SOURCE


def test_gitignore_covers_generated_runtime_artifacts():
    assert "release/" in GITIGNORE_SOURCE
    assert "build_temp/" in GITIGNORE_SOURCE
    assert "data/" in GITIGNORE_SOURCE
    assert "reports/**/*.md" in GITIGNORE_SOURCE
    assert "reports/**/*.csv" in GITIGNORE_SOURCE


def test_settings_page_avoids_direct_database_and_sqlite_calls():
    assert "database." not in SETTINGS_PAGE_SOURCE
    assert "sqlite3" not in SETTINGS_PAGE_SOURCE


def test_reports_page_avoids_direct_exporter_calls():
    assert "exporter." not in REPORTS_PAGE_SOURCE


def test_software_stats_page_avoids_direct_database_and_exporter_calls():
    assert "database." not in SOFTWARE_STATS_PAGE_SOURCE
    assert "exporter." not in SOFTWARE_STATS_PAGE_SOURCE


def test_category_stats_page_avoids_direct_database_calls():
    assert "database." not in CATEGORY_STATS_PAGE_SOURCE


def test_rule_config_page_avoids_direct_database_calls():
    assert "database." not in RULE_CONFIG_PAGE_SOURCE


def test_wizard_avoids_direct_database_calls():
    assert "database." not in WIZARD_SOURCE


def test_main_window_avoids_direct_database_and_exporter_calls():
    assert "database.query_" not in MAIN_WINDOW_SOURCE
    assert "database.get_random_poetry" not in MAIN_WINDOW_SOURCE
    assert "exporter." not in MAIN_WINDOW_SOURCE


def test_main_window_handles_settings_restart_requests():
    assert ".restart_requested.connect(self._restart_app)" in MAIN_WINDOW_SOURCE
    assert "command = current_launch_command()" in MAIN_WINDOW_SOURCE
    assert "stop_recording_worker_safely(self.worker)" in MAIN_WINDOW_SOURCE
    assert "schedule_restart(command, deferred=True)" in MAIN_WINDOW_SOURCE


def test_main_window_schedules_background_report_backfill():
    assert "ReportBackfillWorker" in MAIN_WINDOW_SOURCE
    assert "QTimer.singleShot(15000, self._start_report_backfill)" in MAIN_WINDOW_SOURCE


def test_tray_manager_avoids_direct_database_and_exporter_calls():
    assert "database.query_" not in TRAY_MANAGER_SOURCE
    assert "exporter." not in TRAY_MANAGER_SOURCE


def test_command_handlers_avoid_direct_session_persistence_calls():
    for token in ("database.init_db", "database.insert_session", "database.update_session"):
        assert token not in COMMAND_HANDLERS_SOURCE


def test_worker_avoids_direct_session_persistence_calls():
    for token in ("database.init_db", "database.insert_session", "database.update_session", "database.close_db"):
        assert token not in WORKER_SOURCE


def test_gui_bootstrap_avoids_direct_database_calls():
    assert "database." not in GUI_BOOTSTRAP_SOURCE


def test_main_delegates_command_handlers_and_gui_bootstrap():
    assert COMMAND_HANDLERS_SOURCE_PATH.exists()
    assert GUI_BOOTSTRAP_SOURCE_PATH.exists()
    assert "services.command_handlers" in MAIN_SOURCE
    assert "services.gui_bootstrap" in MAIN_SOURCE
    assert "def cmd_start(" not in MAIN_SOURCE
    assert "def cmd_report(" not in MAIN_SOURCE
    assert "def cmd_export(" not in MAIN_SOURCE
    assert "def cmd_weekly(" not in MAIN_SOURCE
    assert "def cmd_monthly(" not in MAIN_SOURCE
    assert "def cmd_gui(" not in MAIN_SOURCE
    assert "def _ensure_single_instance(" not in MAIN_SOURCE
