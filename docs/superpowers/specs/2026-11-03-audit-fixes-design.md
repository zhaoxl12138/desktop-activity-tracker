# Six audit fixes: approved scope

The user approved fixing the six reproduced findings on 2026-11-03. This is a
correctness patch, not a new analytics module or a database migration.

1. Write the correction audit inside the SQLite transaction before commit.
   Audit failure rolls back sessions/rules; override failure retains the existing
   compensation path. Never change any time counter.
2. Replace the incomplete completed-history revision with a deterministic,
   streaming content digest of the selected session/sample rows. Pin both reads
   to one read transaction. Today-only writes must not invalidate history.
3. Reuse local AI-evidence validation without restoring Markdown preview or the
   retired manual AI controls. Regenerated native reports mark stale/unverifiable
   appended summaries, retaining their exact original section. Selection in the
   report center checks freshness in a single-flight background reader, rejects
   obsolete results and shows only actionable short state feedback. Existing
   history is not rewritten merely by selecting/opening it. No API requests.
4. Preserve the best-effort legacy sync API, but add explicit strict error
   propagation for GUI/report jobs. A sync failure cannot be reported as success;
   native source and previous destination survive failure.
5. Restore the selected row's data/actions when returning to a cached report tab.
6. Size category duration labels from their rendered text/font, including updated
   values and DPI/font changes; do not impose a five-character limit.

No recording algorithm, classification policy, schema, reports scheduling,
historical bulk rewrite, CI rollout or broad module refactor is in scope. Use
isolated data for all tests. Keep main's four unrelated untracked files. Verify
targeted tests, full pytest, compileall, GUI smoke, static checks, layouts and the
safe release/restart procedure. Keep a rollback executable; do not push implicitly.
