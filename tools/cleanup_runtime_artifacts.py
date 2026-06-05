from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT_DIRS = {"build", "build_temp", "dist", "DayLens"}
OPTIONAL_ARTIFACT_DIRS = {"release"}


def plan_cleanup(root: Path, *, include_release: bool = False) -> list[Path]:
    target_names = set(DEFAULT_ARTIFACT_DIRS)
    if include_release:
        target_names |= OPTIONAL_ARTIFACT_DIRS
    return sorted(
        root / name
        for name in target_names
        if (root / name).exists() and (root / name).is_dir()
    )


def cleanup_artifacts(root: Path, *, include_release: bool = False, dry_run: bool = True) -> list[Path]:
    planned = plan_cleanup(root, include_release=include_release)
    if dry_run:
        return planned
    for path in planned:
        shutil.rmtree(path)
    return planned


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Clean generated DayLens artifact directories.")
    parser.add_argument("--root", default=str(ROOT), help="Repository root to clean.")
    parser.add_argument("--include-release", action="store_true", help="Also remove release/.")
    parser.add_argument("--apply", action="store_true", help="Delete directories. Default is dry-run.")
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    root = Path(args.root).resolve()
    planned = cleanup_artifacts(root, include_release=args.include_release, dry_run=not args.apply)

    if not planned:
        print("No artifact directories found.")
        return 0

    prefix = "Removed" if args.apply else "Would remove"
    for path in planned:
        print(f"{prefix}: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
