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
SPEC_PATH = ROOT / "DayLens.spec"
DIST_APP_DIR = DIST_DIR / "DayLens"
RELEASE_EXE = RELEASE_DIR / "DayLens.exe"


def _kill_running() -> None:
    """Force-kill all DayLens.exe processes so build artifacts are unlocked."""
    killed = False
    for _ in range(3):
        result = subprocess.run(
            ["taskkill", "/f", "/im", "DayLens.exe"],
            capture_output=True, text=True,
        )
        if "SUCCESS" in result.stdout:
            killed = True
            time.sleep(0.5)
        else:
            break
    if killed:
        print("DayLens process terminated.")


def _reset_directory(path: Path) -> None:
    if path.exists():
        for _ in range(5):
            try:
                shutil.rmtree(path)
                break
            except OSError:
                time.sleep(0.5)
    path.mkdir(parents=True, exist_ok=True)


def build_release() -> None:
    _kill_running()
    _reset_directory(BUILD_TEMP_DIR)
    _reset_directory(RELEASE_DIR)

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
    )

    if not DIST_APP_DIR.exists():
        raise FileNotFoundError(f"Missing bundled app directory: {DIST_APP_DIR}")

    for item in DIST_APP_DIR.iterdir():
        target = RELEASE_DIR / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)

    if not RELEASE_EXE.exists():
        raise FileNotFoundError(f"Missing release executable: {RELEASE_EXE}")

    _create_desktop_shortcut(str(RELEASE_EXE))
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
