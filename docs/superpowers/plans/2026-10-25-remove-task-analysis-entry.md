# Remove Task Analysis Entry Implementation Plan

> **For agentic workers:** Execute inline with superpowers:executing-plans and test-driven-development. Preserve the existing main checkout and all unrelated local changes; do not create a new branch or commit without a new user request.

**Goal:** Remove task-chain UI, settings and application runtime calls while preserving recording, classification, goals, reports and historical derived data.

**Architecture:** Detach the optional task-chain page and cloud jobs from the GUI shell. Keep legacy task service/storage modules for historical goal and report compatibility, without exposing an entry or invoking analysis from the application. Saving AI preferences forces retired task switches off while preserving active AI preferences.

**Tech Stack:** Python, PySide6, pytest, existing canonical release tooling.

---

### Task 1: Retire entry points with failing regressions

**Files:** `tests/test_stage_c_shell.py`, `tests/test_task_intelligence_settings.py`, `tests/test_gui_smoke.py`.

- [x] Run `python -m pytest -q` to establish the current baseline.
- [x] Assert statistics tabs are exactly software, category and goals, and `tasks` is absent from `window.pages`.
- [x] Assert dashboard refresh and goal refresh enqueue no `task:load:` or `task:cloud:` work even when legacy switches are true.
- [x] Replace the obsolete settings-widget switch test with a regression asserting no task checkboxes exist and saving preferences disables both legacy flags without modifying existing decision JSON.
- [x] Run the new regressions and verify failures describe the old exposed entry points.

### Task 2: Detach the task feature

**Files:** `src/daylens/gui/main_window.py`, `src/daylens/gui/pages/statistics.py`, `src/daylens/gui/widgets/intelligence_settings.py`.

- [x] Remove TaskChainPage construction/imports, signal connections, dashboard task refresh, task job methods and task result delivery from MainWindow. Preserve goal refresh and all report/recording branches.
- [x] Simplify StatisticsPage to accept software, category and goal widgets; select tabs by widget identity rather than retired hard-coded positions.
- [x] Remove the two task checkboxes. Save `task_analysis_enabled=False` and `task_cloud_enabled=False`; retain AI classification, reports, behavior analysis and budget controls.
- [x] Update the independent GUI smoke to expect three statistics tabs and no task bridge.
- [x] Run targeted regressions, goal tests, report tests and legacy task service tests.

### Task 3: Document, verify and restart

**Files:** `README.md`, `docs/reviews/2026-10-25-task-analysis-removal-result.md`.

- [x] Replace current README task-feature guidance with a retirement note explaining preserved data and unchanged accounting.
- [x] Run `python -m pytest -q`, `python -m compileall -q src/daylens`, `python tests/test_gui_smoke.py`, GUI smoke at 125%/150% scaling, and `git diff --check`.
- [x] Record actual commands, counts and limitations in the review document.
- [x] Validate an explicit unique workspace-contained destination before archiving the previous release directory; do not remove any user data.
- [x] Build and smoke test with `python tools/build_release.py --stage-only`, then use its existing safe-exit, atomic-publication and shortcut helpers after review. Launch canonical release and verify one responsive process, matching executable hashes and disabled task settings.

### Approved extension: remove task-derived behavior analysis

The user explicitly approved removing candidate-task insertions and same-task continuous duration after the shared behavior-profile dependency was identified.

**Files:** `src/daylens/services/behavior_profile_service.py`, `src/daylens/services/behavior_experiment_service.py`, `src/daylens/gui/widgets/behavior_dialog.py`, `src/daylens/gui/widgets/intelligence_settings.py`, `tests/test_behavior_v18.py`.

- [x] Add regressions that summarization never invokes task grouping and exposes only work/entertainment/ordinary continuity metrics.
- [x] Add regressions that profile/report rendering contains no task-derived metrics or task-based experiment section.
- [x] Retire new insertion-rate experiments, remove their dialog controls and reads, and preserve legacy experiment storage/read/stop compatibility. Existing experiments must return an explicit retirement message without querying new data or producing a comparison.
- [x] Remove task grouping and task metrics from profile summaries; mark the changed profile schema `behavior-v2` while continuing to recognize legacy `behavior-v1` experiment files.
- [x] Keep ordinary continuous-work accounting, trust validation, classification, time counters and historical reports unchanged.

### Scope safeguards

- Never delete or migrate `data/usage.db`, goal/decision JSON, task caches or historical reports.
- Retain task confirmation assignments used by old goals/reports, and retain shared trusted-session validation.
- Do not alter time counters, sampling/idle rules, category policies, AI key storage, report schedule or global budget.
- Legacy source modules remain unexposed and uncalled by the shell for safe rollback; this is application feature removal, not historical-data destruction.
