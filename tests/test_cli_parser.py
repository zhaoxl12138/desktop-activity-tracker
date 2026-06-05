from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from daylens.cli import build_parser  # noqa: E402


def test_cli_parser_exposes_expected_subcommands():
    parser = build_parser()
    subparsers_action = next(
        action for action in parser._actions
        if getattr(action, "choices", None)
    )

    assert {"gui", "start", "today", "report", "export", "weekly", "monthly"} <= set(subparsers_action.choices)
