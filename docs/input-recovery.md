# Keyboard and mouse aggregate recovery

Keyboard measurement windows and mouse percentage snapshots are stored in a durable SQLite queue before network delivery. Every batch has an immutable capture UUID. Batches checkpoint at the existing 60-second upload cadence and on stop. Server receipts make a lost-response retry acknowledge the existing row rather than create another report entry.

Only the existing aggregate statistics are queued: counts, percentages, timing, scores and numeric minute summaries. Raw keyboard events remain in memory; no typed text or raw-key log is added to local storage or uploads. Mouse percentage snapshots keep their existing reporting semantics.

The queue is scoped to the captured project, Auth account, organization, typed profile and input kind. New batches must belong to the currently authorized device and its own visible parent productivity session. A parent session that has not synced yet delays delivery. Permissions and plan failures keep data pending for retry.

The dashboard displays separate keyboard and mouse confirmation status. A local persistence failure stops the affected input capture; it never silently discards a failed batch or reports it uploaded. Pause holds replay. Pending data after stopping retries when tracking next starts under the same authorized identity. Unsaved data before a process crash cannot be reconstructed.

Each input kind has a 32 MiB pending-payload limit. Local SQLite storage is not encrypted. Apply `20260912093359_production_input_capture_receipts.sql` before installing this desktop build. Verify real Windows listeners and offline/restart recovery with the hosted backend before wider rollout. Test account switching, pause/stop, device revocation, disk failure, duplicate retries and existing reports.
