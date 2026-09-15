# Windows desktop 1.1.0 testing candidate

This consolidates the previous packaging PR and the desktop release completion work into one candidate. It targets Windows 10/11 x64. The test installer is unsigned until an actual publisher certificate is configured. Code/build checks and installed-device acceptance are separate.

## Included behavior

- Explicit project/task or General tracking; Start, Pause, Resume and Stop; manual break records and policy-controlled advisory idle reminders.
- Session timestamps include an explicit timezone offset so a Windows local time is not silently interpreted as UTC by the backend.
- Session capture commits its initial checkpoint before starting workers, then checkpoints locally every five seconds independently of provider requests. Recovery retains the original account and organization. Abrupt power loss can still lose the interval since the last successful disk checkpoint; the app never invents elapsed time after that checkpoint.
- Durable screenshot, input aggregate and app/site queues with separate visible synchronization status; policy and authorization checks; device presence and revocation handling.
- Windows lock, session disconnect, sign-out and suspend notifications pause through the existing durable break workflow. Unlock/wake never resumes tracking automatically. If Windows notification registration is unavailable, Start/Resume are unavailable and the employee can save diagnostics. Device-specific suspend delivery still needs physical testing.
- Per-user OS-held single-instance lock prevents two trackers from racing local queues. A Windows mutex also tells Setup to require the tracker to exit before updating; Setup never force-kills a running session.
- Working sidebar actions: tracking/privacy details, last completed session JSON export, update check and privacy-safe setup diagnostics. Current app uses foreground information; the displayed total is explicitly the current session total, not a fabricated daily total.
- Cancelling logout leaves timer/UI refresh active. Confirmed sign-out/quit saves and waits for bounded finalization before closing. Window Close quits; Sign Out returns to login. Resume restores the Pause action.

## Updates, signing and rollback

The app checks only this repository's latest stable GitHub release after an explicit employee action. It validates the version, repository URLs, installer size and required assets. HTTPS redirects are limited to GitHub release hosts; response sizes and download duration are bounded. No employee/backend credentials are sent to GitHub.

A download requires a configured public publisher thumbprint in `app_version.TRUSTED_SIGNERS`. The downloaded installer must match `SHA256SUMS.txt` and pass Windows Authenticode validation against that publisher before being promoted from a temporary file. Failed/partial downloads are removed. Unsigned test candidates cannot bypass the publisher gate. There is no silent installation: stop and quit the tracker before running the verified installer.

For signing, configure `DESKTOP_SIGNING_PFX` and `DESKTOP_SIGNING_PASSWORD` as GitHub Actions secrets and pin the public certificate thumbprint in `app_version.py`. Run the Windows workflow manually with `signed=true`. The private key is imported temporarily; the workflow signs the app, installer and uninstaller, verifies the resulting publisher, and removes temporary signing material. Signed builds refuse fixture backend configuration. No certificate is currently available, so a signed build has not been validated end to end. Hardware/Azure-backed signing requires an adapter rather than an exported PFX.

Repository variables `DESKTOP_SUPABASE_URL` and `DESKTOP_SUPABASE_PUBLIC_KEY` are public desktop configuration only. PR builds deliberately use a fixture. A build containing `BUILD-NOT-CONFIGURED.txt` is packaging evidence and cannot be used for employee login testing. An actual-project build requires approved configuration and a main/manual build. This candidate adds no hosted database migration.

Keep the previous known-good installer and its checksum. To roll back, stop tracking, quit and reinstall that verified version. Never delete or move the per-user queue directory to force an update. Downgrade compatibility must be checked against hosted migrations before rollout; the in-app updater never offers downgrades.

Signing references: [Windows Authenticode verification](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.security/get-authenticodesignature), [Inno Setup application mutex](https://jrsoftware.org/ishelp/topic_setup_appmutex.htm), [signed uninstaller](https://jrsoftware.org/ishelp/topic_setup_signeduninstaller.htm). Lock/suspend handling follows [Windows power notifications](https://learn.microsoft.com/en-us/windows/win32/power/wm-powerbroadcast).

## One final employee test pass

Use the configured candidate and a disposable employee account after the matching hosted migrations are confirmed:

1. Install, sign in, choose a task, Start. Launch the tracker again: the second copy must refuse to start.
2. Check app/input/screenshot data in the web app. Pause/Resume/Stop and compare tracked time and breaks. Changing screenshot policy must affect capture.
3. Cancel Sign Out while tracking; the timer must keep updating. Then sign out and sign in again. Close the window and confirm the process exits after save.
4. Lock/unlock and sleep/wake. Tracking must remain paused until Resume; inspect time and break records.
5. Disconnect/reconnect; stop/restart with pending records. Verify the same-account queue recovers without duplicates and a different account cannot replay it.
6. Revoke the device and verify capture stops. Export the last session; save setup diagnostics; compare the report/version with the build manifest.
7. For a later signed release, verify trusted update download, rejected modified installers and install/rollback while preserving queued records.

Record the installer checksum, app version/commit, Windows version and each result. Optional screenshot blur, retrospective idle correction/approval, payroll and server-managed scheduling are not implemented by this desktop candidate. They must not be described as completed desktop features. Native iPhone/Android clients and non-Windows capture are separate releases.
