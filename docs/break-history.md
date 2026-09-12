# Break history

The existing Pause button pauses all tracking and opens a recorded break. Resume/Stop closes it. The dashboard displays live count and duration, excluded from tracked time. No paid/unpaid category or automatic idle-time deduction is inferred.

Stable UUIDs, UTC device timestamps and monotonic closed-break seconds travel with periodic/final session records through the existing identity-scoped SQLite outbox. Pause and resume are locally checkpointed. A crash during a break leaves an open record; restart does not infer its duration or end. Web session detail shows recorded intervals and distinguishes an unknown end from a currently active break.

Install only after the coordinated web migration `20260912081724_production_tracking_break_history.sql` (and earlier project/task context migration) is applied. Rebuild the package with break_tracker included. Verify pause/resume/stop, offline retry, crash/restart, logout/revocation and system clock adjustment on a staging Windows machine.

This is a recorded-break feature, not payroll approval, idle review or full Hubstaff parity. Session history cannot reconstruct interruptions that were never persisted. Existing subscription/identity/storage restrictions remain separate release gates.
