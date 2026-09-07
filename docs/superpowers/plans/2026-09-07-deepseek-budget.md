# Budgeted DeepSeek implementation plan

**Goal:** Deliver optional AI classification and compressed daily/weekly/monthly reviews within a configurable CNY 4 monthly reservation budget (CNY 1 user headroom).

**Architecture:** Local sampling and time accounting remain authoritative. A bounded independent worker batches unknown titles after 30 active seconds, at most five titles per request and 30 new titles per day. Classification decisions apply prospectively on the recording thread; historical records never change when AI is disabled. Stable cached decisions and confirmed overrides avoid repeat calls. Reports reuse compressed summaries, not raw month-long logs.

**Tech stack:** Python, PySide6, existing Windows credential APIs, HTTPS official DeepSeek endpoint, atomic JSON intelligence state next to canonical runtime data. No second usage database.

## Execution checklist

- [ ] Add secret-safe credential service, bounded non-thinking Flash client, strict JSON validation, and transactional budget reservations. Test malformed/oversized responses, no-key behavior, invalid credentials, interrupted reservations, monthly boundaries and budget exhaustion.
- [ ] Add title sanitization, active-time eligibility, deduplication, five-title batches, 30-title daily cap, persistent explicit corrections and versioned cache. Test context identity, rapid switching, cap, stale results and exclusions.
- [ ] Integrate independent queue with recording lifecycle. Resolve classified context on sampling thread; split only on decision changes. Preserve media restrictions and original counters. Test disabled/failed provider parity and shutdown during requests.
- [ ] Add settings controls for credentials, enable switch, feature-specific switches, budget, exclusions and usage. Add source/reason/correction to live monitor with compact plain text.
- [ ] Add once-daily combined theme/review generation; weekly consumes daily summaries and monthly consumes weekly summaries. Keep native reports and user text intact. Budget all requests including connection tests and uncertain failures.
- [ ] Validate integration and layout, run relevant and full regression tests, compileall and release smoke. Publish only canonical release; verify original DB path remains in use. Never include actual API key in commands, logs or fixtures.

## Acceptance decisions

- AI is disabled until user enables it and enters a local key. No unsolicited uploads during development.
- Current official Flash peak tariff is conservatively reserved: input 3 CNY/million, output 9 CNY/million (2026-09-07). Actual usage settles reservations; missing usage retains reserved cost. Price snapshot is explicit and updateable.
- Input byte length is an upper-bound guard rather than pretending characters equal tokens. Include protocol overhead in reserve. Output token ceiling is sent to API; non-thinking mode is explicit.
- Disabling AI cancels pending work, ignores late responses, and uses original classification for future samples. Existing historical classification stays fixed.
- Pending title batches flush after a bounded wait; a lone eligible title must not wait indefinitely for five items.
- Cache and durable decisions have separate lifetime policies. Deleting reusable cache must not delete user overrides or billed request history.
- Savings estimates are not promises: show actual API usage and conservative billed estimates, stop automatically at budget.

## Verification commands

`python -m pytest -q tests/test_intelligence_budget.py tests/test_intelligence_client.py`

`python -m pytest -q` after integration; `python -m compileall -q src`; `git diff --check`; canonical build via `python tools/build_release.py` after regression passes.

## Implementation checkpoint (2026-09-07)

- Implemented budget reservations/settlement, Windows credentials, non-thinking Flash JSON client, title redaction and hashing, batching, daily caps, cache, manual corrections, prospective tracker integration, settings and report UI, compressed reviews and evidence references.
- Latest full suite: 872 passed. Targeted tracking tests verify AI application and disabling split sessions without grace or historical counter changes; media suggestions remain advisory.
- `compileall` and `git diff --check` succeeded. `tools/check_intelligence_layout.py` exercises 1280x720 using temporary fixture data, saves captures under `tmp/intelligence-layout`, and shuts down background queries safely.
- Latest `python tools/build_release.py --stage-only` completed and passed the bundled startup smoke. It leaves the existing canonical release and recording process untouched.
- Deployment pending: existing PID 44340 continues running `release/DayLens.exe`. Windows Computer Use can find the window but screenshot capture fails with `SetIsBorderRequired 0x80004002`, so no guessed clicks or force-kill were used. User was asked to use the normal Exit action. Recheck process state before publishing staging.
- Live paid API test remains user-controlled: no key was entered, no browsing records transmitted, and tests use fake providers. After deployment, user can save their key locally and run the fixed-text connection test.
- Existing unrelated edits to `today_overview.py` and `test_top_app_icons.py` predate this implementation and remain preserved.

## Deployment verification (2026-09-07 23:30)

- Old PID 44340 exited cleanly at 23:28:10 (runtime diagnostics status `clean`, exit code 0).
- Rechecked staging smoke and canonical database `quick_check=ok` before publishing.
- Moved old release to `release_backup_20260907_ai` for recovery; moved validated staging into the sole normal launch directory `release`.
- New PID 24816 started from `D:/OfficeSoftware/DayLens/release/DayLens.exe` at 23:29:24. Startup log confirms `D:/OfficeSoftware/DayLens/data/usage.db`.
- Read-only verification: session count increased from 20,925 to 20,926, historical range still 2026-06-01 through 2026-09-07; the new session reached 23:30:21. Recording and persistence resumed on the same database.
- AI remains opt-in. User supplies the key through local settings; no live browsing/API upload was performed by the development checks.
