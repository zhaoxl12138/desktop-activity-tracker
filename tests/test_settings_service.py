from __future__ import annotations

import yaml

from daylens import database
from daylens.services import settings_service


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
    )

    assert updated["db_path"] == str(new_db_path)
    assert database.load_settings(str(new_db_path))["sample_interval_seconds"] == "2"
