from __future__ import annotations

from pathlib import Path

from tools.cleanup_runtime_artifacts import DEFAULT_ARTIFACT_DIRS, plan_cleanup


def test_plan_cleanup_lists_existing_artifact_directories(tmp_path: Path):
    (tmp_path / "build").mkdir()
    (tmp_path / "dist").mkdir()
    (tmp_path / "release").mkdir()
    (tmp_path / "src").mkdir()

    planned = plan_cleanup(tmp_path)

    assert tmp_path / "build" in planned
    assert tmp_path / "dist" in planned
    assert tmp_path / "release" not in planned
    assert tmp_path / "src" not in planned


def test_default_artifact_dirs_keep_release_out_of_default_cleanup():
    assert "release" not in DEFAULT_ARTIFACT_DIRS
    assert {"build", "build_temp", "dist", "DayLens"}.issubset(DEFAULT_ARTIFACT_DIRS)
