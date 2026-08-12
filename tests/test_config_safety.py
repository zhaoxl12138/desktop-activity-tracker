from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
import yaml

import daylens
from daylens import database
from daylens import utils as daylens_utils
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


def test_legacy_user_config_remains_available_when_migration_write_fails(
    tmp_path, monkeypatch
):
    user_path = _use_temp_data_dir(monkeypatch, tmp_path)
    user_path.write_text("theme: light\n", encoding="utf-8")
    monkeypatch.setattr(
        daylens_utils,
        "_atomic_write_user_config",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            OSError("read-only data directory")
        ),
    )

    loaded = load_user_config()

    assert loaded["theme"] == "light"


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


def test_get_data_dir_reuses_project_data_from_frozen_worktree(tmp_path, monkeypatch):
    workspace = tmp_path / "DayLens"
    worktree_root = workspace / ".worktrees" / "trusted-metrics-insights"
    worktree_root.mkdir(parents=True)
    shared_data = workspace / "data"
    shared_data.mkdir()
    (shared_data / "usage.db").touch()
    (worktree_root / "data").mkdir()
    (worktree_root / "data" / "usage.db").touch()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(worktree_root))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "local"))

    assert daylens.get_data_dir() == str(shared_data)


def test_get_data_dir_reuses_project_data_from_source_worktree(tmp_path, monkeypatch):
    workspace = tmp_path / "DayLens"
    worktree_root = workspace / ".worktrees" / "rhythm-card"
    worktree_root.mkdir(parents=True)
    shared_data = workspace / "data"
    shared_data.mkdir()
    (shared_data / "usage.db").touch()
    (worktree_root / "data").mkdir()
    (worktree_root / "data" / "usage.db").touch()

    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(daylens, "get_app_root", lambda: str(worktree_root))

    assert daylens.get_data_dir() == str(shared_data)


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


def test_settings_service_resolves_default_database_to_selected_data_directory(
    tmp_path, monkeypatch
):
    selected_data = tmp_path / "local" / "DayLens"
    monkeypatch.setattr(daylens, "get_data_dir", lambda: str(selected_data))
    monkeypatch.setattr(
        settings_service.database,
        "merge_db_settings",
        lambda *_args: None,
    )
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "db_path: data/usage.db\ntheme: dark\ncategories: {}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_service, "load_user_config", lambda: {})

    loaded = settings_service.load_page_config(
        str(config_path),
        str(selected_data / "usage.db"),
    )

    assert settings_service.normalize_database_path("data/usage.db") == str(
        selected_data / "usage.db"
    )
    assert loaded["db_path"] == str(selected_data / "usage.db")


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


def test_invalid_database_settings_cannot_override_validated_config(
    tmp_path, monkeypatch
):
    config_path = tmp_path / "config.yaml"
    db_path = tmp_path / "usage.db"
    config_path.write_text(
        yaml.safe_dump(
            {
                "theme": "dark",
                "db_path": str(db_path),
                "sample_interval_seconds": 3,
                "tracker": {
                    "sample_interval_seconds": 3,
                    "idle_threshold_seconds": 60,
                },
                "categories": {},
            }
        ),
        encoding="utf-8",
    )
    _use_temp_data_dir(monkeypatch, tmp_path)
    save_user_config({"theme": "light", "db_path": str(db_path)})
    database.init_db(str(db_path)).close()
    conn = __import__("sqlite3").connect(db_path)
    conn.executemany(
        "INSERT OR REPLACE INTO settings(key, value) VALUES (?, ?)",
        [
            ("theme", "neon"),
            ("sample_interval_seconds", "-4"),
            ("idle_threshold_seconds", "999999"),
        ],
    )
    conn.commit()
    conn.close()

    loaded = load_config(str(config_path))

    assert loaded["theme"] == "light"
    assert loaded["sample_interval_seconds"] == 3
    assert loaded["tracker"]["sample_interval_seconds"] == 3
    assert loaded["tracker"]["idle_threshold_seconds"] == 60


def test_tracked_factory_config_contains_no_personal_absolute_paths():
    factory_path = Path(__file__).resolve().parents[1] / "config" / "config.yaml"
    factory = yaml.safe_load(factory_path.read_text(encoding="utf-8"))

    assert factory["db_path"] == "data/usage.db"
    assert factory.get("obsidian_output_path", "") == ""
    serialized = factory_path.read_text(encoding="utf-8").casefold()
    assert "d:\\officesoftware" not in serialized
    assert "c:\\users\\administrator" not in serialized


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
