# Office Category Consistency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Count the `office` category as productive work everywhere.

**Architecture:** Extend every existing work-category set and SQL list with `office`, backed by behavior and consistency tests.

**Tech Stack:** Python, SQLite, pytest.

---

- [ ] Add `tests/test_office_work_category.py`: assert dashboard aggregation counts office; category detail requests office; a range query with an office session reports work seconds; exporter no longer contains the legacy four-key SQL/set literals.
- [ ] Run the new tests and verify RED.
- [ ] Add office to `dashboard_service.WORK_KEYS`, `category_stats_service` work sources, all exporter work sets/SQL lists, and `stats_repository` range SQL.
- [ ] Run focused and full tests plus compileall.
- [ ] Commit, fast-forward merge, rebuild, refresh shortcuts, restart, and verify the release process.
