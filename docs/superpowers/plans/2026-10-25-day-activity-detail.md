# Near-seven-day full-day activity detail implementation

**Approved goal:** Click an individual day in either seven-day work or entertainment chart to open one read-only 00:00–24:00 overview with chronological event details. Default details are effective activity >=300 seconds, with an all-events toggle. No AI, task inference, accounting changes or database migration.

**Architecture:** Interval repository query -> pure day activity builder -> asynchronous isolated dialog. Original session counters remain the source of truth. Chart cards expose ISO-date signals; the home shell opens one shared dialog restricted to the captured seven-day date list.

**Execution:** Reuse the user-requested current main checkout and preserve all unrelated uncommitted changes. Use test-first development and review gates. Do not commit/push unless asked.

## Tasks

- [x] Data service and interval query: test threshold boundaries, exact same-title adjacency, switches, idle, gaps, versions, legacy, midnight allocation, duplicate/conflicting/overlapping records, empty/future/query failure, read-only access.
- [x] Chart entry: add ISO dates to the work seven-day payload; add day_activated(str) on both cards, with full day-column hit targets including zero/missing values. No click action in other modes; preserve tooltips.
- [x] Dialog: date controls, refresh, all-day colored foreground-span timeline and chronological long-event table; all-events toggle and row selection highlighting. Distinguish unknown/idle/future/unreliable and explain mixed idle/legacy rows.
- [x] Async/lifecycle: bounded single-flight background read, latest request wins, immutable worker inputs and no Qt access from worker; closing stops delivery without blocking recording.
- [x] Shell integration: both home cards relay the date and open one dialog with snapshot seven-day ISO dates and configured sample interval/display resolver. No homepage polling/query increase.
- [x] Verify targeted and full pytest, compileall, GUI smoke 100/125/150%, synthetic 1280x720 and 1920x1080 layout screenshots, spec and quality reviews.
- [x] Build isolated release, safe-exit and publish with canonical helpers, retain previous release, restart exactly one responsive DayLens instance; record true results in docs/reviews.

## Fixed data rules

Grouping requires same process, normalized title, category, metric and classification version. Only adjacent rows with a gap no larger than one configured sample interval capped at two seconds may merge; intervening app/title/idle/excluded evidence blocks grouping. Never add gap duration to effective totals. Timeline geometry uses recorded foreground ranges, not guessed active timestamps. Cross-day counters use existing exact integer-weight allocation. Legacy engaged/passive are unknown, not invented. Conflicting/overlapping evidence is explicitly unavailable for credible event time, rather than silently double-counted.
