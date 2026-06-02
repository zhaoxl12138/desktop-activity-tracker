from __future__ import annotations

import sys
from pathlib import Path

import daylens


def _write_project_config(root: Path) -> None:
    config_dir = root / "config"
    config_dir.mkdir()
    (config_dir / "config.yaml").write_text("db_path: data/usage.db\n", encoding="utf-8")


def test_get_app_root_uses_project_root_for_onedir_build(monkeypatch, tmp_path):
    _write_project_config(tmp_path)
    exe_dir = tmp_path / "dist" / "DayLens"
    exe_dir.mkdir(parents=True)

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "DayLens.exe"))

    assert daylens.get_app_root() == str(tmp_path)


def test_get_app_root_uses_project_root_for_onefile_build(monkeypatch, tmp_path):
    _write_project_config(tmp_path)
    exe_dir = tmp_path / "dist2"
    exe_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "DayLens.exe"))

    assert daylens.get_app_root() == str(tmp_path)


def test_get_app_root_uses_exe_dir_for_installed_copy(monkeypatch, tmp_path):
    exe_dir = tmp_path / "DayLens"
    exe_dir.mkdir()

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe_dir / "DayLens.exe"))

    assert daylens.get_app_root() == str(exe_dir)
