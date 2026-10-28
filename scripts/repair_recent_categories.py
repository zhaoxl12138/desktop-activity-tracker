"""Preview or apply the audited recent-category repair."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from daylens.services.historical_category_repair_service import (  # noqa: E402
    apply_repair,
    preview_repair,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    result = (
        apply_repair(args.db, args.start, args.end)
        if args.apply
        else preview_repair(args.db, args.start, args.end)
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
