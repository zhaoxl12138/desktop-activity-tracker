# Untitled Tencent Video Playback Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans with test-driven development and verification checkpoints.

**Goal:** Prevent unrelated audio or unknown evidence from crediting an untitled Tencent Video window, and correct only the approved historical session.

**Architecture:** Keep the compatibility detector for other contexts. For an untitled `QQLive.exe` window in the video category, consume the existing structured playback evidence at the tracker boundary; pass the matching process/title at each call site. Change only the three counters in the verified historical row in one SQLite transaction.

**Tech Stack:** Python, Windows Core Audio, pytest, SQLite, existing DayLens release tool.

- [x] Add tracker regression coverage in `tests/test_session_tracker_policies.py` and run `python -m pytest -q tests/test_session_tracker_policies.py -k tencent` to observe the false passive credit.
- [x] Update `src/daylens/session_tracker.py` to require `PlaybackState.PLAYING` with `source == "target_peak"` for the scoped window, and pass window context from the active, pending and snapshot paths. Fail closed if a failed session write leaves a Tencent session with another foreground process. Verified 99 targeted tests, 1,491 full pytest tests, compileall, Ruff E9/F821, GUI smoke and independent review.
- [ ] Review and commit the source change, fast-forward local `main`, and build/smoke/publish with `python tools/build_release.py`, preserving the former release.
- [ ] Verify the exact approved row before updating. Back up with `create_database_backup`; revalidate with `BEGIN IMMEDIATE`; set `effective_seconds=68, passive_seconds=0, idle_seconds=9477` only for the unchanged row. Verify the backup and post-update counters, retain a local audit, restart visibly, and check recorder health.
