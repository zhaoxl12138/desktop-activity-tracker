from __future__ import annotations

from pathlib import Path

import yaml

import daylens
from daylens.utils import save_user_config


ROOT = Path(__file__).resolve().parents[1]


def test_pyproject_uses_daylens_entrypoint_and_clean_description():
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

    assert 'desktop-activity-tracker = "daylens.main:main"' in text
    assert 'description = "Windows desktop activity tracking and analysis"' in text


def test_save_user_config_can_remove_stale_override(tmp_path, monkeypatch):
    monkeypatch.setattr(daylens, "get_data_dir", lambda: str(tmp_path))
    user_path = tmp_path / "user_config.yaml"
    user_path.write_text(
        "obsidian_output_path: E:/old/month\ndb_path: D:/data/usage.db\n",
        encoding="utf-8",
    )

    save_user_config({}, remove_keys={"obsidian_output_path"})

    saved = yaml.safe_load(user_path.read_text(encoding="utf-8"))
    assert "obsidian_output_path" not in saved
    assert saved["db_path"] == "D:/data/usage.db"

