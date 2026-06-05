from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_TEMP_DIR = ROOT / "build_temp"
RELEASE_DIR = ROOT / "release"
SPEC_PATH = ROOT / "DayLens.spec"
DIST_APP_DIR = DIST_DIR / "DayLens"
RELEASE_EXE = RELEASE_DIR / "DayLens.exe"


def _reset_directory(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def build_release() -> None:
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

    print(f"Release prepared at: {RELEASE_DIR}")


if __name__ == "__main__":
    build_release()
