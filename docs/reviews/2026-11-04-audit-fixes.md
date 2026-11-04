# Six audit fixes — verification

Base: `3a5e22c`. Implementation verified at `a48b106`. No migration, accounting
algorithm, classification-policy, or bulk history/report rewrite was added.
Tests use isolated data, and freshness verification never invokes an AI provider.

## Automated verification

- Baseline `python -m pytest -q`: 1,445 passed in 36.82 s.
- Before fixes, new tests reproduced audit persistence partial commit, cache
  false hits, absent freshness feedback, incorrect sync success, cached selection
  mismatch, and duration clipping. Review added red tests for snapshot races,
  stale file identity and sync races, CRLF preservation, and partial failures.
- Final focused suite of report freshness/preview, history cache, Obsidian,
  report jobs/service/page, connections, interface cleanup and duration: 115 passed.
- Final worktree `python -m pytest -q`: 1,482 passed in 48.56 s.
- `python -m compileall -q src tests tools`, `python -m ruff check src tests tools
  --select E9,F821`, `python tests/test_gui_smoke.py`, `git diff --check`: passed.
- Layout scripts `check_navigation_layout.py`, `check_reports_v2_layout.py`,
  `check_day_activity_layout.py`, and `check_audit_fixes_layout.py`: passed at
  1280×720 and 1920×1080, 100%, 125%, 150%, in dark/light. Inspected the 150%
  compact report warning and complete `1200时59分` label captures.

## Review and performance

The independent first pass caught separate digest/load snapshots, stale
same-path file results, CRLF normalization, and sync race/partial-failure paths.
They are covered by isolated regressions in `15f0cc5`. The final reader keeps
legacy sample checks in SQLite rather than serializing the per-tick rows.
Follow-up review reproduced cross-process vault publication and a double I/O
failure; `a48b106` adds the per-destination Windows mutex and separates native
quick-report generation from strict synchronization. The final independent
review passed 60 targeted tests, including the two-process test, and reported
no remaining merge blockers.

Five-run, synthetic 30-day fingerprint benchmark:

- 172,800 legacy rows: median 30.77 ms, max 47.11 ms. Independent baseline
  57–66 ms; initial all-row Python digest 891–1,001 ms.
- 9,000 session rows plus 172,800 legacy rows: median 105.60 ms, max 121.34 ms.
- Digest runs off the GUI thread; existing refresh cadence unchanged. Legacy
  samples are append/delete-only in DayLens. External in-place modifications to
  legacy samples are not a supported cache invalidation path.

## Local publication and restart

- Local `main` fast-forwarded to `bc38de9`. Merged `python -m pytest -q`:
  1,482 passed in 55.89 s. Unrelated untracked files were left alone.
- `python tools/build_release.py` completed with bundled Qt and disposable
  credentials smoke checks. The package includes `win32event.pyd`.
- Old PID 15512 exited cleanly at 14:23:25 +08:00, exit code 0. New formal
  release PID 22748 opened at 14:23:52 +08:00 with a responding DayLens
  window. The first regular 60-second heartbeat at 14:24:52 confirmed running.
  A read-only SQLite check saw three session rows flushed after restart,
  with latest end time 14:25:16. No historical rows were edited by verification.
- Release/dist executable SHA-256:
  `90953F256067C9AC390B02E439E71AC7947F311EDC41B8525E4610519B13D4BB`.
- Immediate rollback `release_previous/DayLens.exe` SHA-256:
  `C8398A15B9C65ED2FC91CB6965F8DE9649DD460367BEB996799D4C64D8B57006`.
  The older rollback was moved to `release_previous_20261104_before_audit_fixes`.
- No push was performed.
