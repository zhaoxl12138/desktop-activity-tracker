from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_TEMP_DIR = ROOT / "build_temp"
RELEASE_DIR = ROOT / "release"
RELEASE_STAGING_DIR = ROOT / "release_staging"
RELEASE_PREVIOUS_DIR = ROOT / "release_previous"
SPEC_PATH = ROOT / "DayLens.spec"
DIST_APP_DIR = DIST_DIR / "DayLens"
RELEASE_EXE = RELEASE_DIR / "DayLens.exe"
_QT_SMOKE_ENV = "DAYLENS_QT_SMOKE"


def _sanitized_build_environment(source: dict[str, str] | None = None) -> dict[str, str]:
    """Remove host-agent dependency directories from the PyInstaller PATH."""
    env = dict(os.environ if source is None else source)
    path_entries = env.get("PATH", "").split(os.pathsep)
    env["PATH"] = os.pathsep.join(
        entry
        for entry in path_entries
        if "codex-runtimes" not in entry.casefold()
    )
    return env


def _validate_dist_runtime() -> None:
    """Reject app-local Windows UCRT/API-set DLLs that can shadow the OS."""
    internal = DIST_APP_DIR / "_internal"
    contaminated = sorted(
        path.name
        for path in internal.glob("*.dll")
        if path.name.casefold() == "ucrtbase.dll"
        or path.name.casefold().startswith("api-ms-win-")
    )
    if contaminated:
        raise RuntimeError(
            "Contaminated Windows runtime DLLs in bundle: "
            + ", ".join(contaminated)
        )


def _stop_running_gracefully() -> None:
    """Request a normal close, using force only when a process will not exit."""
    for _ in range(3):
        result = subprocess.run(
            ["taskkill", "/im", "DayLens.exe"],
            capture_output=True, text=True,
        )
        if "SUCCESS" not in result.stdout:
            return
        time.sleep(0.5)

    for _ in range(5):
        result = subprocess.run(
            ["tasklist", "/fi", "IMAGENAME eq DayLens.exe"],
            capture_output=True, text=True,
        )
        if "DayLens.exe" not in result.stdout:
            return
        time.sleep(0.5)

    subprocess.run(
        ["taskkill", "/f", "/im", "DayLens.exe"],
        capture_output=True,
        text=True,
        check=False,
    )


def _smoke_test(exe_path: Path) -> None:
    """Import Qt and initialize its platform plugin in the bundled runtime."""
    env = dict(os.environ)
    env[_QT_SMOKE_ENV] = "1"
    subprocess.run(
        [str(exe_path)],
        cwd=exe_path.parent,
        capture_output=True,
        timeout=20,
        check=True,
        env=env,
    )


def _remove_directory(path: Path, *, required: bool) -> bool:
    for _ in range(8):
        if not path.exists():
            return True
        try:
            shutil.rmtree(path)
            return True
        except OSError:
            time.sleep(0.5)
    if required:
        raise OSError(f"Unable to remove release directory: {path}")
    print(f"[WARN] Old rollback directory retained: {path}")
    return False


def _publish_staging() -> None:
    """Atomically swap the prepared release, retaining the old version for rollback."""
    if RELEASE_PREVIOUS_DIR.exists():
        _remove_directory(RELEASE_PREVIOUS_DIR, required=True)
    if RELEASE_DIR.exists():
        os.replace(RELEASE_DIR, RELEASE_PREVIOUS_DIR)
    try:
        os.replace(RELEASE_STAGING_DIR, RELEASE_DIR)
    except Exception:
        if RELEASE_PREVIOUS_DIR.exists() and not RELEASE_DIR.exists():
            os.replace(RELEASE_PREVIOUS_DIR, RELEASE_DIR)
        raise
    if RELEASE_PREVIOUS_DIR.exists():
        _remove_directory(RELEASE_PREVIOUS_DIR, required=False)


def _copy_dist_to_staging() -> None:
    _reset_directory(RELEASE_STAGING_DIR)
    for item in DIST_APP_DIR.iterdir():
        target = RELEASE_STAGING_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def _reset_directory(path: Path) -> None:
    if path.exists():
        for _ in range(5):
            time.sleep(0.5)
            try:
                shutil.rmtree(path)
                break
            except OSError:
                time.sleep(0.5)
    path.mkdir(parents=True, exist_ok=True)


def build_release() -> None:
    _reset_directory(BUILD_TEMP_DIR)
    _reset_directory(DIST_DIR)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            str(SPEC_PATH),
            "--noconfirm",
            "--distpath",
            str(DIST_DIR),
            "--workpath",
            str(BUILD_TEMP_DIR),
        ],
        cwd=ROOT,
        check=True,
        env=_sanitized_build_environment(),
    )

    if not DIST_APP_DIR.exists():
        raise FileNotFoundError(f"Missing bundled app directory: {DIST_APP_DIR}")

    if not (DIST_APP_DIR / "DayLens.exe").exists():
        raise FileNotFoundError(f"Missing bundled executable: {DIST_APP_DIR / 'DayLens.exe'}")

    _validate_dist_runtime()

    _copy_dist_to_staging()
    staging_exe = RELEASE_STAGING_DIR / "DayLens.exe"
    _smoke_test(staging_exe)
    _stop_running_gracefully()
    _publish_staging()

    _create_desktop_shortcut(str(RELEASE_DIR / "DayLens.exe"))
    print(f"Release prepared at: {RELEASE_DIR}")


def _create_desktop_shortcut(exe_path: str) -> None:
    """Create (or refresh) a desktop shortcut for DayLens."""
    import os

    try:
        from win32com.client import Dispatch
    except ImportError:
        return

    desktop = os.path.join(os.environ.get("USERPROFILE", ""), "Desktop")
    if not os.path.isdir(desktop):
        return

    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortcut(os.path.join(desktop, "DayLens.lnk"))
    shortcut.TargetPath = exe_path
    shortcut.WorkingDirectory = os.path.dirname(exe_path)
    shortcut.Description = "DayLens"
    shortcut.Save()
    print(f"Desktop shortcut created: {desktop}\\DayLens.lnk")


if __name__ == "__main__":
    build_release()
