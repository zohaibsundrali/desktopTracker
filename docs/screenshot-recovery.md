# Private screenshot recovery

This phase makes the existing desktop screenshot flow recoverable. It preserves the configured capture cadence and PNG/JPEG behavior; it does not introduce a new employee/admin privacy policy, change screenshot visibility, or silently enable a disabled screenshot feature.

A capture is permitted only while its worker is running, its shared controller is neither paused nor stopped, and the original typed Auth login is still current. The worker checks again after the OS capture and after image encoding. A pause, stop or account switch during those operations discards the uncommitted image. Already-started remote requests cannot be recalled, but later upload steps stop when authorization or the controller changes.

Each accepted image receives a full UUID capture ID and immutable private path:

```
monitoring/{organization_id}/{developer_id}/capture_{capture_id}.{jpg|png}
```

The worker commits the image bytes, SHA-256 digest and original metadata in one SQLite transaction **before network upload**. The database is scoped to project URL, Auth subject, organization, profile ID and profile type. It never stores tokens or public image URLs. The same identity may recover it after re-login; another identity cannot replay it.

Recovery uses the existing authenticated private Storage endpoint, followed by `finalize_screenshot_capture(p_capture_id, p_metadata)`. `20260912070957_production_idempotent_screenshot_capture.sql` in the web repository must be applied before deploying this desktop version. Storage creates the fixed path without overwriting objects. If a previous response was lost and the object already exists, authenticated download must match the saved byte length and SHA-256 digest before recovery proceeds. The local uploaded marker survives restart, so a failed metadata step can retry independently. Metadata acknowledgment must confirm the exact capture ID and storage path before local bytes are deleted.

Replay starts with the worker and runs after captures, subject to the same pause/authorization gate. A process-wide and cross-process OS lock prevents simultaneous replay of one identity's queue. Each replay handles at most 25 records and loads one image at a time. Corrupt bytes remain flagged for recovery while healthy captures continue. The cached status exposes pending count and bytes; the dashboard shows the pending count, last successful synchronization time and a generic error status.

## Operational limits and privacy boundaries

- Image transport limits are **6 MiB and 16,384 pixels per dimension**, matching the backend contract. Oversized images fail visibly before queuing; no implicit resizing or quality changes occur.
- The local screenshot backlog has a **256 MiB byte budget per identity/project**. A full queue or failed disk stops further screenshot capture; existing saved images remain. This is local resource backpressure, not a subscription entitlement or retention policy.
- Local files are stored under the OS user's application-data directory in `screenshot-outbox/`, with restrictive POSIX modes. SQLite uses `synchronous=FULL` and `secure_delete=ON`. It is **not encrypted at rest**, and these settings do not guarantee forensic erasure on SSDs, backups or snapshots.
- Saved images are retained until confirmed upload. No automatic local age-based deletion policy has been invented. Revoked/expired identities and backend quota/history denials can leave a backlog requiring authorized recovery or a separately approved deletion policy.
- Storage and metadata are separate provider transactions. An object can temporarily exist without metadata after a failure. The durable record allows retry; this release does not introduce a quota-reservation or cross-service transaction. Backend Storage/device/plan policies and metadata quota guards still apply.
- If an already-confirmed Storage object is subsequently removed before metadata finalization, its server existence check prevents acknowledgment. Such a record remains for investigation; recovery does not silently recreate intentionally deleted images.

## Validation and rollout

```sh
python -m unittest discover -s tests -v
```

Tests use synthetic byte strings, fake image encoders and mocked HTTP only. They cover process termination during upload, durable phase recovery, identity isolation, immutable capture IDs, hash checks after ambiguous Storage responses, corrupt-record handling, account changes between requests, pause/stop races, storage failure and size limits. No OS screenshots or hosted uploads execute.

Deploy the screenshot-finalization migration, verify its grants/guards in staging, and then rebuild the desktop installer. `tracker.spec` includes the new outbox/upload/limits modules and the existing SQLite extension. Windows locking/packaging, real screenshot formats, network recovery, provider policy rejection, deletion/retention behavior and reconnect after token expiry require staging/Windows verification. Offline tests do not certify those external conditions.
