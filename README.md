# Verisade desktop tracker

Windows 10/11 x64 desktop tracker, version 1.1.2. This source candidate still
requires the matching hosted database repairs, a signed build and installed
Windows acceptance. The source archive does not contain an accepted installer.
See [the release guide](docs/desktop-release-candidate.md) before distribution.

## Development

The Windows build workflow uses Python 3.12. From PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
# Set the intended project's Supabase URL and public anon key in .env.
.\.venv\Scripts\python main.py
```

Only public backend configuration belongs in the installed application. Never
embed a Supabase service-role key, employee password or signing private key.
The website and desktop must target the same project, with the tracker ownership
and receipt migrations applied. Capture requires an authorized employee account
and enrolled device; Windows-specific capture cannot be certified on Linux.

## Verification and release

```powershell
.\.venv\Scripts\python -m unittest discover -s tests
```

`scripts/verify_sync.py --help` describes the real hosted transport check. Run it
only with disposable QA accounts and private configuration. It exercises durable
queues with synthetic samples, checks readback and denial cases, and records
cleanup results. It does not replace physical keyboard/mouse, lock, suspend or
installed offline-recovery acceptance.

The GitHub Actions Windows workflow installs `requirements-build.txt`, runs the
tests and UI checks, builds the installer, and records a release manifest. Follow
the [release guide](docs/desktop-release-candidate.md) for actual backend settings,
publisher signing, acceptance, stable release assets and rollback. For Microsoft
Store packaging, follow [the separate submission guide](docs/verisade-store-submission.md).
Preserve employee queues during upgrades and rollback.

The accompanying website handover report records the two pending hosted database
repairs and the current download/deployment blockers. A passing source test suite
does not establish that these external release steps are complete.
