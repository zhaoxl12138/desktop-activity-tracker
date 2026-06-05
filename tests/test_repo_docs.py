from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_readme_mentions_layout_doc_and_runtime_dirs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "docs/repository-layout.md" in readme
    assert "tools/build_release.py" in readme
    assert "tools/cleanup_runtime_artifacts.py" in readme
    for required in ("src/", "tests/", "data/", "reports/", "release/"):
        assert required in readme


def test_repository_layout_doc_mentions_generated_artifacts():
    text = (ROOT / "docs" / "repository-layout.md").read_text(encoding="utf-8")
    for required in ("build/", "build_temp/", "dist/", "release/", "DayLens/"):
        assert required in text
    assert "tools/cleanup_runtime_artifacts.py" in text
    assert "dry-run" in text


def test_editorconfig_declares_utf8_for_repo_text_files():
    editorconfig = (ROOT / ".editorconfig").read_text(encoding="utf-8")
    assert "charset = utf-8" in editorconfig
    assert "end_of_line = lf" in editorconfig
    assert "[*.{py,md,toml,yaml,yml,txt}]" in editorconfig


def test_repository_uses_single_packaging_spec():
    assert (ROOT / "DayLens.spec").exists()
    assert not (ROOT / "DayLensNew.spec").exists()
