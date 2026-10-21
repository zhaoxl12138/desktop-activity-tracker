# Stage D Reliability and Performance Result

## Delivered

- Added monotonic sample-interval observations and three-state playback evidence (`playing`, `paused`, `unknown`).
- Preserved the existing boolean playback adapter and fixed-duration accounting, so this release does not silently change trusted totals.
- Added an atomic, aggregate-only shadow log under the canonical data `logs` directory. It stores counts, delay buckets, states, and evidence source names only—never titles, applications, paths, URLs, or PIDs.
- Cached repeated canonical timestamp parsing and session validation without changing snapshot values.
- Prevented identical dashboard payloads from rebuilding widgets.
- Moved periodic software/category statistics reads off the GUI thread; hidden tabs do not query, and software selection/scroll survives changed results.
- Split the live day from completed historical evidence. Completed ranges are cached by date and a database revision fingerprint that includes metric/classification versions; current-day data remains live.
- Disabled production computation of the retired homepage `trend` and `goals` models while retaining compatibility-shaped fields for one cycle.
- Removed the product-date constant from the 30-day chart start; its range now begins with the actual first recorded date inside the rolling window.
- Added daily/weekly/monthly report metadata: period, data-updated time, deterministic report generation time, and local AI appendix status. No additional AI request was introduced.

## Measured result

Database: `data/usage.db`, 23,195,648 bytes at baseline.

- Instrumented pre-optimization snapshot: median 1,650.29 ms, p95 1,820.52 ms, 10 read statements, ~6.0 MB Python peak allocation.
- Final warm snapshot benchmark (9 runs, tracing excluded from latency): median 59.66 ms, 7 read statements, 1,732,359-byte single-run Python peak allocation.
- Cold first load: 279.83 ms and 12 read statements; completed history is then reused until its revision fingerprint changes.

## Verification

- Focused measurement/audio/worker tests: 50 passed.
- Focused dashboard tests: 98 passed during optimization.
- Focused report tests: 59 passed.
- Full suite: 989 passed in 21.26 seconds.
- `compileall`: passed.
- `git diff --check`: no whitespace errors; only existing Windows line-ending notices.
- Initial online database backup: `data/backups/20261020-stage-d/usage.db`; final pre-publish backup: `data/backups/20261021-stage-d-final/usage.db`; both passed `PRAGMA quick_check = ok`.
- Packaged Qt and credential smoke tests: passed.
- Published executable: `release/DayLens.exe` (verified running as the only DayLens process, PID 69456); canonical database remains `data/usage.db` and recorded a new packaged-run session after startup.

## Deliberately deferred until evidence exists

- No formal “large sampling gap” threshold was selected.
- `unknown` playback grace behavior was not changed.
- GPU/network activity was not promoted to accounting evidence.
- GPU/network evidence and a formal unknown-playback grace policy remain deferred.

## Shadow evidence after the first long run

- 18,957 sample intervals observed.
- 18,956 were at or below 1.25× the configured cadence.
- One suspend-like interval was approximately 17,284 seconds and coincided with one wall-clock rollback.
- Playback evidence contained only three observations (one target-silent pause and two unattributed global-silent unknowns), which is insufficient to change playback accounting safely.

Review the shadow distribution after normal work, video playing/paused/muted, background music, multiple players, lock/unlock, sleep/resume, and crash recovery have all occurred. Only then should accounting policy change.
