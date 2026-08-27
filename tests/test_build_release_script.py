from __future__ import annotations

from pathlib import Path
import importlib.util


ROOT = Path(__file__).resolve().parents[1]


def _load_build_release_module():
    path = ROOT / "tools" / "build_release.py"
    spec = importlib.util.spec_from_file_location("daylens_build_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_build_release_script_defines_release_as_publish_target():
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "DayLens.spec" in script
    assert "release" in script
    assert "DayLens.exe" in script


def test_build_release_script_publishes_from_staging_and_keeps_rollback():
    script = (ROOT / "tools" / "build_release.py").read_text(encoding="utf-8")

    assert "release_staging" in script
    assert "release_previous" in script
    assert "os.replace" in script
    assert "DAYLENS_QT_SMOKE" in script
    assert "taskkill" in script


def test_build_environment_removes_codex_runtime_dependency_paths():
    module = _load_build_release_module()
    contaminated = (
        r"C:\Windows\System32;"
        r"C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime"
        r"\dependencies\native\libheif\libheif\bin;"
        r"C:\Tools\bin"
    )

    result = module._sanitized_build_environment({"PATH": contaminated})

    assert "codex-runtimes" not in result["PATH"].casefold()
    assert r"C:\Windows\System32" in result["PATH"]
    assert r"C:\Tools\bin" in result["PATH"]


def test_runtime_validation_rejects_app_local_ucrt(tmp_path, monkeypatch):
    module = _load_build_release_module()
    internal = tmp_path / "_internal"
    internal.mkdir()
    (internal / "ucrtbase.dll").write_bytes(b"contaminated")
    monkeypatch.setattr(module, "DIST_APP_DIR", tmp_path)

    try:
        module._validate_dist_runtime()
    except RuntimeError as exc:
        assert "ucrtbase.dll" in str(exc)
    else:
        raise AssertionError("app-local UCRT contamination was accepted")

