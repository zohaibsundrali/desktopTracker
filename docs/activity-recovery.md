# App/site offline recovery

App and browser usage are cumulative snapshots per tracking-session/app or tracking-session/site. Live and closed segments use one aggregate, preventing separate inserts and reopened-app counter resets. Snapshots are saved durably on the polling loop before network delivery.

The SQLite outbox is scoped to the captured project/Auth/organization/profile identity. Revisions persist across process restarts. Exact acknowledgment clears only that snapshot; a newer revision is never removed by an older reply. Corrupt entries stay available for recovery while healthy entries can progress. Confirmed payloads are replaced with minimal hashed revision/duration receipts; local storage is not encrypted and compaction is not a forensic erasure guarantee.

The queue caps pending payloads at64MiB and total receipt keys at100000. A storage failure stops app/site capture and shows an error; it does not silently stop the shared timer or other capture workers. Repair storage and start a fresh tracking session to resume app/site capture.

Pause holds network replay. Stop saves the final memory snapshot and makes at most one final-row upload attempt under the original login, bounded by a10-second request timeout. Remaining pending snapshots retry during the next authorized tracking session. A saved parent productivity session must be visible before the backend accepts new activity; otherwise the queue retries later. Unobserved/unsaved time before a crash cannot be reconstructed.

Before installing, run the web preflight scripts/sql/activity-aggregate-preflight.sql and resolve any returned historical duplicates safely. Then apply migration20260912084740_production_activity_aggregate_receipts.sql. Rebuild with activity_outbox/activity_upload packaged. Verify real Windows capture, close/reopen aggregation, offline/restart recovery, account changes, pause/stop, duplicate response handling and quota failures on staging. Keyboard/mouse detailed telemetry recovery is separate work.
