"""Console encoding helpers for Windows-friendly CLI output."""

from __future__ import annotations

import sys
from types import SimpleNamespace


def configure_console_encoding(streams: object | None = None) -> None:
    target = streams or sys
    for name in ("stdout", "stderr"):
        stream = getattr(target, name, None)
        encoding = getattr(stream, "encoding", None)
        if stream is None or not encoding or encoding.upper() == "UTF-8":
            continue
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            continue

