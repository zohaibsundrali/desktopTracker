# Durable productivity-session synchronization

The desktop queues periodic productivity-session checkpoints and completed sessions in SQLite **before** uploading. Files live in the current OS user's data directory under `session-outbox/`. The queue uses SQLite transactions with `synchronous=FULL`; a row is removed only after the server returns the matching session ID, organization and profile. An ambiguous response or process crash leaves the same session ID available for retry. Fresh sessions use UUID-based IDs and the existing server `session_id` upsert contract.

Each queue is scoped to the Supabase project URL, Auth subject, organization, profile ID and profile type captured at login. Tokens are never stored in it. A later verified login for that same identity can replay it; other identities cannot. Upload request headers explicitly retain their captured bearer token even if the SDK's shared defaults change during logout. Supabase still validates the token, device, permissions and subscription on every request. These local checks do not replace backend authorization.

Uploads are serialized by a nonblocking OS file lock, including across application processes; the OS releases the lock if the uploader crashes. New checkpoints can be committed during an upload. Acknowledging an older payload cannot remove a newer one. A small terminal-ID table prevents late periodic callbacks from reopening a completed session, even after successful upload. These UUID-only terminal markers currently remain on disk indefinitely; do not prune them while callbacks or other processes could still reference those sessions.

Replay runs at startup, after a new checkpoint is saved, and every 60 seconds while that login remains authorized. Failures stay queued. The dashboard shows pending count, successful synchronization time, storage/retry errors and legacy recovery status. Disk initialization failure prevents tracking from starting; a subsequent local write failure stops capture and displays an error rather than claiming that the session was safely saved.

The old `.pending_sessions.jsonl` file is preserved **byte for byte**. Its rows do not reliably contain the original Auth subject, typed identity or project, so they are never guessed into the new identity's queue. Existing legacy records require explicit operator investigation and verified identity recovery. No legacy file is silently deleted, truncated or uploaded.

## Scope and verification

This phase covers `productivity_sessions` only. It does not provide offline queues for screenshots, keyboard/mouse detail, app/browser usage or arbitrary API requests. An abrupt crash can still lose capture since the latest periodic checkpoint (normally 60 seconds). It cannot recover data already discarded by older releases or a failed disk. SQLite durability relies on the operating system and storage honoring synchronization. Local files use OS-user directory isolation and restrictive POSIX modes; they are not encrypted at rest.

Run the complete offline suite with the pinned dependencies installed:

```sh
python -m unittest discover -s tests -v
```

Tests exercise real local SQLite files, process termination mid-upload, rollback, concurrent writers/drains, identity isolation, late periodic updates, ambiguous acknowledgments, legacy preservation, constructor initialization and failed storage. The real pinned Supabase SDK test intercepts HTTP locally and proves account switches cannot change an already-built queued request's bearer token. No production requests or capture APIs execute.

`tracker.spec` explicitly includes the outbox and SQLite modules. Rebuild and test the Windows distribution to verify the bundled SQLite extension, Windows locking and actual OS shutdown/network-loss behavior. Live staging verification must also confirm the deployed `productivity_sessions.session_id` conflict key and its existing RLS/device/plan rules, including reconnect after expiry and same-user replay after re-login. Offline mocks do not certify those hosted conditions.
