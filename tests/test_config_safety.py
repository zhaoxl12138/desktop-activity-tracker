from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

import daylens
from daylens import database
from daylens.gui.main_window import MainWindow
from daylens.runtime import load_config
from daylens.services import settings_service
from daylens.utils import (
    generate_default_config,
    load_user_config,
    save_user_config,
)

USER_CONFIG_VERSION = 1


def _use_temp_data_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setattr(daylens, "get_data_dir", lambda: str(tmp_path))
    return tmp_path / "user_config.yaml"


def test_save_user_config_filters_invalid_and_unknown_values(tmp_path, monkeypatch):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)

    save_user_config(
        {
            "theme": "light",
            "db_path": 123,
            "obsidian_output_path": "D:/Notes",
            "machine_secret": "must-not-persist",
        }
    )

    stored = yaml.safe_load(user_path.read_text(encoding="utf-8"))
    assert stored == {
        "config_version": USER_CONFIG_VERSION,
        "theme": "light",
        "obsidian_output_path": "D:/Notes",
    }


def test_save_user_config_is_atomic_and_keeps_last_known_good_backup(
    tmp_path, monkeypatch
):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)
    save_user_config({"theme": "dark"})
    first = user_path.read_bytes()

    save_user_config({"theme": "light"})

    assert load_user_config()["theme"] == "light"
    assert user_path.with_suffix(".yaml.bak").read_bytes() == first
    assert not user_path.with_suffix(".yaml.tmp").exists()


def test_save_user_config_replace_failure_preserves_primary(tmp_path, monkeypatch):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)
    save_user_config({"theme": "dark"})
    original = user_path.read_bytes()
    real_replace = os.replace

    def fail_primary_replace(source, destination):
        if os.fspath(destination) == os.fspath(user_path):
            raise OSError("replace failed")
        return real_replace(source, destination)

    monkeypatch.setattr(os, "replace", fail_primary_replace)
    with pytest.raises(OSError, match="replace failed"):
        save_user_config({"theme": "light"})

    assert user_path.read_bytes() == original
    assert not user_path.with_suffix(".yaml.tmp").exists()


def test_load_user_config_recovers_corrupt_primary_from_backup(tmp_path, monkeypatch):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)
    user_path.write_text("theme: [broken", encoding="utf-8")
    user_path.with_suffix(".yaml.bak").write_text(
        f"config_version: {USER_CONFIG_VERSION}\ntheme: light\n",
        encoding="utf-8",
    )

    loaded = load_user_config()

    assert loaded["theme"] == "light"
    assert yaml.safe_load(user_path.read_text(encoding="utf-8"))["theme"] == "light"


def test_load_user_config_migrates_legacy_allowlisted_values(tmp_path, monkeypatch):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)
    user_path.write_text(
        "theme: dark\ndb_path: D:/DayLens/usage.db\nunknown: old\n",
        encoding="utf-8",
    )

    loaded = load_user_config()

    assert loaded == {
        "config_version": USER_CONFIG_VERSION,
        "theme": "dark",
        "db_path": "D:/DayLens/usage.db",
    }
    assert yaml.safe_load(user_path.read_text(encoding="utf-8")) == loaded


def test_save_page_config_never_rewrites_factory_config(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    factory = "theme: dark\ndb_path: data/usage.db\ncategories: {}\n"
    config_path.write_text(factory, encoding="utf-8")
    user_calls = []
    monkeypatch.setattr(
        settings_service,
        "save_user_config",
        lambda values, remove_keys=None: user_calls.append((values, remove_keys)),
    )

    updated = settings_service.save_page_config(
        config_path=str(config_path),
        db_path=str(tmp_path / "old.db"),
        config={"theme": "dark", "db_path": "data/usage.db", "tracker": {}},
        sample_interval=2,
        idle_threshold=90,
        startup_enabled=True,
        new_db_path=str(tmp_path / "new.db"),
        obsidian_output_path="D:/Notes",
    )

    assert config_path.read_text(encoding="utf-8") == factory
    assert updated["sample_interval_seconds"] == 2
    assert user_calls[0][0]["db_path"] == str(tmp_path / "new.db")


def test_main_window_theme_persistence_never_rewrites_factory_config(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.yaml"
    factory = "theme: dark\ncategories: {}\n"
    config_path.write_text(factory, encoding="utf-8")
    captured = []
    monkeypatch.setattr(
        "daylens.utils.save_user_config", lambda values: captured.append(values)
    )
    window_like = type(
        "WindowLike",
        (),
        {"config_path": str(config_path), "current_theme": "light"},
    )()

    MainWindow._persist_theme_preference(window_like)

    assert config_path.read_text(encoding="utf-8") == factory
    assert captured == [{"theme": "light"}]


def test_get_data_dir_keeps_existing_frozen_install_state(tmp_path, monkeypatch):
    legacy_data = tmp_path / "data"
    legacy_data.mkdir()
    (legacy_data / "usage.db").touch()
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert daylens.get_data_dir() == str(legacy_data)


def test_get_data_dir_uses_local_appdata_for_new_frozen_install(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(tmp_path / "install"))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert daylens.get_data_dir() == str(tmp_path / "local" / "DayLens")


def test_get_data_dir_keeps_project_data_for_source_run(tmp_path, monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(tmp_path))

    assert daylens.get_data_dir() == str(tmp_path / "data")


def test_default_relative_database_path_uses_selected_data_directory(
    tmp_path, monkeypatch
):
    selected_data = tmp_path / "local" / "DayLens"
    monkeypatch.setattr(daylens, "get_data_dir", lambda: str(selected_data))
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(tmp_path / "install"))

    resolved = database.get_db_path({"db_path": "data/usage.db"})

    assert resolved == str(selected_data / "usage.db")


def test_generate_default_config_is_deterministic_without_app_scan(
    tmp_path, monkeypatch
):
    def forbidden_scan():
        raise AssertionError("factory config must not scan this computer")

    monkeypatch.setattr(
        "daylens.app_scanner.scan_installed_apps", forbidden_scan
    )
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"

    generate_default_config(str(first))
    generate_default_config(str(second))

    assert first.read_bytes() == second.read_bytes()


def test_load_config_merges_factory_user_then_database(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        yaml.safe_dump(
            {
                "theme": "dark",
                "db_path": str(tmp_path / "usage.db"),
                "sample_interval_seconds": 1,
                "tracker": {"sample_interval_seconds": 1},
                "categories": {},
            }
        ),
        encoding="utf-8",
    )
    _use_temp_data_dir(monkeypatch, tmp_path)
    save_user_config({"theme": "light", "db_path": str(tmp_path / "usage.db")})
    database.init_db(str(tmp_path / "usage.db")).close()
    database.save_settings(
        str(tmp_path / "usage.db"),
        {"theme": "dark", "sample_interval_seconds": 7},
    )

    loaded = load_config(str(config_path))

    assert loaded["theme"] == "dark"
    assert loaded["sample_interval_seconds"] == 7
    assert loaded["tracker"]["sample_interval_seconds"] == 7


def test_load_page_config_ignores_invalid_user_mapping(tmp_path, monkeypatch):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "theme: dark\ndb_path: data/usage.db\ncategories: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_service, "load_user_config", lambda: ["bad"])
    monkeypatch.setattr(settings_service.database, "merge_db_settings", lambda *_: None)

    loaded = settings_service.load_page_config(
        str(config_path), str(tmp_path / "usage.db")
    )

    assert loaded["theme"] == "dark"
