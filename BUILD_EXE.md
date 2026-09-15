# Windows desktop build and acceptance

Full app/window capture is supported on Windows 10/11. A Linux build cannot
produce a Windows executable. Windows setup tests and real capture acceptance
are separate from the offline Python regression suite.

## Public configuration

The pinned Supabase 1.1.1 SDK accepts a **legacy anon JWT key**, not modern
`sb_publishable_` keys. Use the anon key for the application's Supabase project.
RLS, signed-in user authorization and enrolled-device policies remain required.
Never include a service-role key, database password or user access/refresh token.

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=<legacy anon key>
```

`python scripts/prepare_public_config.py` validates these values and writes only
allowlisted configuration to `build/public-config/.env`. It does not copy a
whole developer `.env`; unknown fields are excluded and private/session keys
are rejected. Failed validation removes an earlier generated config so the
wrong project's previous bundle cannot be reused. Environment variables take
precedence over the source `.env`; interpolation is disabled.

Apply the reviewed application migrations in their release order. Existing
tracking policies require an authenticated, enrolled device; do not replace
them with broad policies to work around a permission error.

For live device presence, first apply the companion web repository migration
`20260912154948_production_tracker_device_presence.sql`. Then build this desktop
version, install it, and sign in. Verify start, pause, resume and stop in the
monitoring dashboard. Heartbeats continue every 30 seconds while paused;
without a heartbeat, the dashboard marks the device disconnected after 90
seconds. The old desktop build cannot report this new presence signal.

## Local Windows build

Install Python 3.12 and Inno Setup 6, then run:

```bat
build_exe.bat
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
```

The app is `dist\DeveloperTracker\DeveloperTracker.exe`. The installer is
`Output\DeveloperTracker-Setup.exe`. Dependency/config/build failures stop the
batch command rather than claiming that a stale executable is a successful build.
The default installer is an explicitly marked unsigned testing candidate. The
optional signing pipeline and verified update download are described in
[the release candidate guide](docs/desktop-release-candidate.md). No signing
certificate is currently configured.

## GitHub Windows build

The Windows desktop build workflow runs the Python regression suite, prepares
public configuration, freezes the app, runs its packaged offline diagnostics,
and compiles the installer. It uploads a 14-day artifact named with the commit
SHA containing the installer, SHA-256 checksum, version manifest and diagnostics report.

For main/manual builds, repository variables `DESKTOP_SUPABASE_URL` and
`DESKTOP_SUPABASE_PUBLIC_KEY` configure the public project and legacy anon key.
PR builds and builds with missing configuration use a non-working fixture and
include `BUILD-NOT-CONFIGURED.txt`. Those artifacts prove packaging only and
must not be distributed to employees. No production credentials, captures,
emails, enrolled devices or payment requests are used by the workflow.

## Offline setup diagnostics

Run from PowerShell and wait for the windowed process to finish:

```powershell
Start-Process -Wait -FilePath '.\dist\DeveloperTracker\DeveloperTracker.exe' -ArgumentList '--diagnostics', 'desktop-diagnostics.json'
Get-Content desktop-diagnostics.json
```

The report checks supported platform, public configuration, required imports and
writable per-user storage. It never starts event listeners, takes screenshots,
logs in, contacts the backend or includes user names, window titles or keys.
A passing result means **ready for manual testing**, not confirmed live tracking.
Runtime queues and remembered email use the per-user data directory, not Program
Files. Unavailable storage must be corrected; there is no shared-directory fallback.

## Installed Windows acceptance

Use a disposable staff account and verify the matching web/database releases
before testing. The latest device-presence migration is
`20260912154948_production_tracker_device_presence.sql`; check the migration
history before applying it, and do not replay an old bundle.

1. Install, sign in and confirm device enrollment and writable per-user storage.
2. Select a project/task and start tracking. Compare web and desktop attribution.
3. Pause, resume and stop. Confirm breaks exclude tracked time, new capture pauses,
   and connected/paused device status is distinct from historical activity.
4. Disable screenshots in organization policy and verify new capture stops.
5. Disconnect the network, record activity, then reconnect. Confirm recovery
   without duplicate screenshots/input/app aggregates or double-counted time.
6. Restart after queued work. Confirm own-account recovery and account isolation.
7. Sign out/revoke the device. Verify capture stops and revoked credentials cannot
   submit new records. Check monitoring access using a different organization.
8. Close/disconnect the app and verify web presence expires after 90 seconds.

Record the app commit, Windows version, test date and pass/fail results. A CI
artifact or a successful homepage deploy cannot substitute for this journey.

The version is generated from `app_version.py` using `python scripts/prepare_version.py`. Keep the existing installer AppId to preserve upgrade identity. Setup refuses to replace an app holding its running mutex; it does not force-close tracking. Uninstall and upgrade leave per-user pending queues intact.
