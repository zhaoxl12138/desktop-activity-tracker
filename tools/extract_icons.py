#!/usr/bin/env python3
"""Batch extract application icons from installed software.

Usage:
    python tools/extract_icons.py              # extract all scanned apps
    python tools/extract_icons.py --missing     # only extract missing icons
    python tools/extract_icons.py code.exe      # extract single app
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import QFileInfo
from PySide6.QtWidgets import QApplication, QFileIconProvider


def _find_exe_path(process_name: str, install_dir: str | None = None) -> str | None:
    """Find the full path to an executable by name."""
    # Try install_dir first
    if install_dir:
        candidate = os.path.join(install_dir, process_name)
        if os.path.isfile(candidate):
            return candidate

    # Search common locations
    search_dirs = [
        os.environ.get("ProgramFiles", "C:\\Program Files"),
        os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)"),
        os.path.expandvars(r"%LOCALAPPDATA%\Programs"),
        os.path.expandvars(r"%APPDATA%"),
    ]
    for base in search_dirs:
        if not os.path.isdir(base):
            continue
        for root, dirs, files in os.walk(base):
            # Limit depth for performance
            depth = root[len(base):].count(os.sep)
            if depth > 3:
                dirs.clear()
                continue
            for fname in files:
                if fname.lower() == process_name.lower():
                    return os.path.join(root, fname)

    # Try running processes
    try:
        import psutil
        for proc in psutil.process_iter(attrs=["name", "exe"]):
            try:
                if (proc.info.get("name") or "").lower() == process_name.lower():
                    exe = proc.info.get("exe")
                    if exe and os.path.exists(exe):
                        return exe
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except ImportError:
        pass

    return None


def extract_icon(exe_path: str, output_path: str, size: int = 32) -> bool:
    """Extract icon from an .exe and save as PNG. Returns True on success."""
    info = QFileInfo(exe_path)
    if not info.exists():
        return False

    provider = QFileIconProvider()
    icon = provider.icon(info)
    if icon.isNull():
        return False

    pixmap = icon.pixmap(size, size)
    if pixmap.isNull():
        return False

    pixmap.save(output_path, "PNG")
    return True


def main():
    parser = argparse.ArgumentParser(description="Extract app icons to assets/icons/")
    parser.add_argument("--missing", action="store_true",
                        help="Only extract icons that don't already exist")
    parser.add_argument("--size", type=int, default=32,
                        help="Icon size in pixels (default: 32)")
    parser.add_argument("target", nargs="?", type=str,
                        help="Process name to extract (e.g. code.exe), or omit for all")
    args = parser.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    icons_dir = os.path.join(project_root, "assets", "icons")
    os.makedirs(icons_dir, exist_ok=True)

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)

    from daylens.app_scanner import scan_installed_apps

    apps = scan_installed_apps()

    if args.target:
        target_lower = args.target.lower()
        if target_lower in apps:
            apps = {target_lower: apps[target_lower]}
        else:
            apps = {target_lower: None}

    total = len(apps)
    extracted = 0
    skipped = 0
    failed = 0

    for process_name, install_dir in sorted(apps.items()):
        output_path = os.path.join(icons_dir, f"{process_name}.png")

        if args.missing and os.path.exists(output_path):
            skipped += 1
            continue

        exe_path = _find_exe_path(process_name, install_dir)
        if exe_path is None:
            print(f"  SKIP  {process_name} — exe not found")
            failed += 1
            continue

        if extract_icon(exe_path, output_path, args.size):
            extracted += 1
            if total <= 20 or extracted % 10 == 0:
                print(f"  OK    {process_name} ({extracted}/{total})")
        else:
            print(f"  FAIL  {process_name} — icon extraction failed")
            failed += 1

    print(f"\nDone: {extracted} extracted, {skipped} skipped, {failed} failed "
          f"(total: {total})")
    print(f"Icons saved to: {icons_dir}")


if __name__ == "__main__":
    main()
