from __future__ import annotations

import yaml
import pytest

import daylens
from daylens import database
from daylens.services import settings_service


def test_normalize_database_path_resolves_relative_path(monkeypatch, tmp_path):
    monkeypatch.setattr(
        daylens,
        "get_data_dir",
        lambda: str(tmp_path / "data"),
    )

    result = settings_service.normalize_database_path("data/new.db")

    assert result == str(tmp_path / "data" / "new.db")


def test_empty_database_path_does_not_overwrite_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    original = "db_path: original.db\n"
    config_path.write_text(original, encoding="utf-8")
    monkeypatch.setattr(settings_service, "save_user_config", lambda *args, **kwargs: None)

    with pytest.raises(ValueError, match="不能为空"):
        settings_service.save_page_config(
            config_path=str(config_path),
            db_path=str(tmp_path / "current.db"),
            config={"db_path": "original.db", "tracker": {}},
            sample_interval=1,
            idle_threshold=60,
            startup_enabled=False,
            new_db_path="",
            obsidian_output_path="",
        )

    assert config_path.read_text(encoding="utf-8") == original


def test_save_page_config_initializes_a_new_database(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    old_db_path = tmp_path / "old.db"
    new_db_path = tmp_path / "new" / "usage.db"
    config = {
        "db_path": str(old_db_path),
        "obsidian_output_path": "",
        "tracker": {"sample_interval_seconds": 1, "idle_threshold_seconds": 60},
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")
    monkeypatch.setattr(settings_service, "save_user_config", lambda *args, **kwargs: None)

    updated = settings_service.save_page_config(
        config_path=str(config_path),
        db_path=str(old_db_path),
        config=config,
        sample_interval=2,
        idle_threshold=90,
        startup_enabled=False,
        new_db_path=str(new_db_path),
        obsidian_output_path="",
        weekday_entertainment_limit_minutes=75,
        weekend_entertainment_limit_minutes=0,
    )

    assert updated["db_path"] == str(new_db_path)
    saved = database.load_settings(str(new_db_path))
    assert saved["sample_interval_seconds"] == "2"
    assert saved["weekday_entertainment_limit_minutes"] == "75"
    assert saved["weekend_entertainment_limit_minutes"] == "0"
