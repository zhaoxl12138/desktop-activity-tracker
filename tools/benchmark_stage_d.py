"""Read-only Stage D dashboard benchmark.

Reports latency, executed SQL statements, and Python peak allocations.  It does
not write application settings or database rows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
import tracemalloc
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from daylens.runtime import load_config  # noqa: E402
from daylens.services.dashboard_service import load_today_snapshot  # noqa: E402


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def benchmark(db_path: Path, config: dict, runs: int) -> dict:
    original_connect = sqlite3.connect
    sql_counts: list[int] = []
    latencies: list[float] = []

    for _ in range(max(1, runs)):
        count = 0

        def traced_connect(*args, **kwargs):
            connection = original_connect(*args, **kwargs)

            def trace(statement):
                nonlocal count
                if statement.lstrip().upper().startswith(("SELECT", "PRAGMA", "WITH")):
                    count += 1

            connection.set_trace_callback(trace)
            return connection

        sqlite3.connect = traced_connect
        started = time.perf_counter()
        try:
            load_today_snapshot(
                str(db_path),
                lambda process, _details: process,
                config,
            )
        finally:
            elapsed = (time.perf_counter() - started) * 1000
            sqlite3.connect = original_connect
        latencies.append(elapsed)
        sql_counts.append(count)

    tracemalloc.start()
    load_today_snapshot(
        str(db_path),
        lambda process, _details: process,
        config,
    )
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    return {
        "database": str(db_path.resolve()),
        "database_bytes": db_path.stat().st_size,
        "runs": len(latencies),
        "latency_ms": {
            "median": round(statistics.median(latencies), 2),
            "p95": round(_percentile(latencies, 0.95), 2),
            "samples": [round(value, 2) for value in latencies],
        },
        "read_sql_count": {
            "median": statistics.median(sql_counts),
            "max": max(sql_counts),
            "samples": sql_counts,
        },
        "python_peak_bytes_single_run": peak,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(ROOT / "data" / "usage.db"))
    parser.add_argument("--config", default=str(ROOT / "config" / "config.yaml"))
    parser.add_argument("--runs", type=int, default=7)
    args = parser.parse_args()
    config = load_config(args.config)
    print(json.dumps(benchmark(Path(args.db), config, args.runs), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
