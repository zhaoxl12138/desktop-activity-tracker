# Software Export Target Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Save software-stat CSV and Markdown exports exactly to the user-selected file path.

**Architecture:** Generate through the existing exporter inside a temporary directory, copy the generated artifact to the normalized target, and return the final path.

**Tech Stack:** Python tempfile/shutil, SQLite, pytest.

---

- [ ] Add `tests/test_software_stats_export.py` with an initialized temporary database and custom CSV/Markdown targets; assert returned paths equal the targets and both files exist.
- [ ] Run the new tests and verify RED because current functions return only basenames and do not create the chosen files.
- [ ] Add a private `_export_to_target(export_func, db_path, target_path)` in `software_stats_service.py` using `TemporaryDirectory`, `os.path.abspath`, `os.makedirs`, and `shutil.copy2`.
- [ ] Route both export functions through the helper and return the final absolute target.
- [ ] Update software-page status text to display the returned path.
- [ ] Run focused tests, then full pytest and compileall.
- [ ] Commit, fast-forward to main, rebuild, refresh shortcuts, restart, and verify one release process.
