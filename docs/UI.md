# Desktop Activity Tracker UI Notes

## Dark Dashboard Direction

The current Dashboard uses a restrained dark theme instead of a decorative skin. The goal is to improve long-term readability while keeping the app focused on local activity analysis.

## Current Layout

- Sidebar: product name, short positioning text, and existing feature navigation.
- Top bar: current page title, date, daily summary, pause/resume, and report generation.
- Dashboard body: metric cards, time distribution, efficiency score, focus blocks, daily timeline, and top apps.
- Bottom bar: recording state, latest sample time, and quit action.

## Design Rules

- Do not add user systems, Pro badges, cloud sync, or comparative claims that the product cannot support.
- Keep all business logic, database logic, and sampling logic separate from visual changes.
- Prefer shared theme constants in `src/desktop_activity_tracker/gui/style.py`.
- New dashboard widgets should remain reusable and isolated under `src/desktop_activity_tracker/gui/widgets/`.

## Color Semantics

- Total usage: blue.
- Study/work: green.
- Social: purple.
- Video/entertainment: orange.
- Idle: gray.
- Warnings: red.

## Next UI Work

- Improve timeline hover/details after the current report data path is stable.

## 2026-06-01 Follow-up

Non-home pages now share the dark table, tab, input, group, and card language. Remaining UI work should focus on automated regression checks and targeted readability improvements instead of another broad theme pass.

## GUI Smoke Check

Run `python tests/test_gui_smoke.py` before UI commits. It starts the main window with a temporary database/config, switches every visible navigation page, toggles pause/resume, and saves a dashboard screenshot in a temporary directory to catch default-size layout regressions.
