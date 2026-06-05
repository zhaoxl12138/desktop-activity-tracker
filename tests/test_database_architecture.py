from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATABASE_SOURCE = (ROOT / "src" / "daylens" / "database.py").read_text(encoding="utf-8")
EXPORTER_SOURCE = (ROOT / "src" / "daylens" / "exporter.py").read_text(encoding="utf-8")
TIMELINE_SOURCE = (ROOT / "src" / "daylens" / "timeline.py").read_text(encoding="utf-8")
SETTINGS_SERVICE_SOURCE = (ROOT / "src" / "daylens" / "services" / "settings_service.py").read_text(encoding="utf-8")


def test_database_delegates_settings_and_rules_storage():
    settings_repo = ROOT / "src" / "daylens" / "repositories" / "settings_repository.py"
    assert settings_repo.exists()
    assert "repositories.settings_repository" in DATABASE_SOURCE
    assert "def load_settings(" not in DATABASE_SOURCE
    assert "def save_settings(" not in DATABASE_SOURCE
    assert "def merge_db_settings(" not in DATABASE_SOURCE
    assert "def load_custom_rules(" not in DATABASE_SOURCE
    assert "def save_custom_rules(" not in DATABASE_SOURCE
    assert "def merge_custom_rules(" not in DATABASE_SOURCE


def test_database_delegates_stats_query_implementations():
    stats_repo = ROOT / "src" / "daylens" / "repositories" / "stats_repository.py"
    assert stats_repo.exists()
    assert "repositories.stats_repository" in DATABASE_SOURCE
    assert "def _query_date_stats_from_logs(" not in DATABASE_SOURCE
    assert "def _query_date_stats_from_sessions(" not in DATABASE_SOURCE
    assert "def _query_date_range_from_sessions(" not in DATABASE_SOURCE
    assert "def _query_date_range_from_logs(" not in DATABASE_SOURCE


def test_database_delegates_connection_and_schema_management():
    connection_repo = ROOT / "src" / "daylens" / "repositories" / "connection_repository.py"
    assert connection_repo.exists()
    assert "repositories.connection_repository" in DATABASE_SOURCE
    assert "SCHEMA =" not in DATABASE_SOURCE
    assert "class _TrackedConnection" not in DATABASE_SOURCE
    assert "class _read_conn_ctx" not in DATABASE_SOURCE
    assert "def init_shared_read_conn(" not in DATABASE_SOURCE
    assert "def close_shared_read_conn(" not in DATABASE_SOURCE
    assert "def init_db(" not in DATABASE_SOURCE
    assert "def close_db(" not in DATABASE_SOURCE


def test_database_delegates_session_writes():
    session_repo = ROOT / "src" / "daylens" / "repositories" / "session_repository.py"
    assert session_repo.exists()
    assert "repositories.session_repository" in DATABASE_SOURCE
    assert "def insert_activity_log(" not in DATABASE_SOURCE
    assert "def insert_session(" not in DATABASE_SOURCE
    assert "def update_session(" not in DATABASE_SOURCE


def test_database_delegates_remaining_query_routes_and_poetry():
    stats_repo = ROOT / "src" / "daylens" / "repositories" / "stats_repository.py"
    poetry_repo = ROOT / "src" / "daylens" / "repositories" / "poetry_repository.py"
    assert stats_repo.exists()
    assert poetry_repo.exists()
    assert "repositories.poetry_repository" in DATABASE_SOURCE
    assert "def query_date(" not in DATABASE_SOURCE
    assert "def query_session_entertainment_trend(" not in DATABASE_SOURCE
    assert "def query_entertainment_trend(" not in DATABASE_SOURCE
    assert "def query_session_count(" not in DATABASE_SOURCE
    assert "def query_today_sessions(" not in DATABASE_SOURCE
    assert "def query_category_detail(" not in DATABASE_SOURCE
    assert "def count_consecutive_days(" not in DATABASE_SOURCE
    assert "def query_date_range_stats(" not in DATABASE_SOURCE
    assert "def get_random_poetry(" not in DATABASE_SOURCE
    assert "def get_poetry_count(" not in DATABASE_SOURCE


def test_exporter_timeline_and_settings_service_avoid_direct_sqlite_access():
    assert "sqlite3.connect(" not in EXPORTER_SOURCE
    assert "sqlite3.connect(" not in TIMELINE_SOURCE
    assert "sqlite3.connect(" not in SETTINGS_SERVICE_SOURCE
