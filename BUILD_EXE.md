# Building the Windows installer (`Setup.exe`)

This turns the Python app into a normal Windows program that a user can
**download → double-click → install** — no Python needed on their machine.

The pipeline is two stages:

1. **PyInstaller** bundles the app into `dist\DeveloperTracker\DeveloperTracker.exe`
2. **Inno Setup** wraps that folder into a single `DeveloperTracker-Setup.exe`

> ⚠️ **Must be done on a Windows machine.** A Windows `.exe` cannot be built on
> Linux/Mac. Use a Windows 10/11 PC (or a Windows VM).

---

## 🔴 STEP 0 — Security (do this BEFORE building, it is not optional)

The build bundles your `.env` **inside the app**, so it ships to every user who
downloads it. Include only desktop public configuration. A `service_role`,
secret API key, database password or other private credential must never be
included; packaged files can be extracted by users.

Before building, edit `.env` so it uses the **anon / publishable** key instead:

```
SUPABASE_URL=https://isaccqqjobuwfeaxlrwc.supabase.co
SUPABASE_KEY=<your ANON / publishable key>
```

Get the anon key: Supabase dashboard → Project Settings → **API** → `anon` `public`.

Apply the reviewed application migrations in their release order. Existing
tracking policies require an authenticated, enrolled device; do not replace
them with broad policies to work around a permission error.

For live device presence, first apply the companion web repository migration
`20260912154948_production_tracker_device_presence.sql`. Then build this desktop
version, install it, and sign in. Verify start, pause, resume and stop in the
monitoring dashboard. Heartbeats continue every 30 seconds while paused;
without a heartbeat, the dashboard marks the device disconnected after 90
seconds. The old desktop build cannot report this new presence signal.

---

## STEP 1 — Install the tools (one time)

1. **Python 3.11 or 3.12** — https://www.python.org/downloads/
   (tick *"Add Python to PATH"* during install)
2. **Inno Setup** (free) — https://jrsoftware.org/isdl.php

---

## STEP 2 — Build the `.exe`

Open **Command Prompt** in the project folder and run:

```bat
build_exe.bat
```

This installs dependencies + PyInstaller and builds the app. When it finishes you
get:

```
dist\DeveloperTracker\DeveloperTracker.exe
```

Double-click that `.exe` to test it runs (login window should appear).

> Optional icon: put a `app.ico` file in the project folder before building and
> it is picked up automatically (also uncomment `SetupIconFile` in `installer.iss`).

---

## STEP 3 — Build the installer (`Setup.exe`)

1. Open **Inno Setup Compiler**
2. **File → Open** → `installer.iss`
3. Press **Build → Compile** (or the ▶ button)

Output:

```
Output\DeveloperTracker-Setup.exe
```

That single file is what you upload to your website. The user downloads it,
double-clicks, clicks **Next → Install**, and the app installs with a Start-menu
(and optional desktop) shortcut plus an uninstaller in "Add/Remove Programs".

---

## STEP 4 — Put it on your website

Upload `DeveloperTracker-Setup.exe` and link a **Download** button to it, e.g.:

```html
<a href="/downloads/DeveloperTracker-Setup.exe" download>Download for Windows</a>
```

### ⚠️ "Windows protected your PC" (SmartScreen)
Because the installer is **unsigned**, Windows shows a blue SmartScreen warning
the first time. Users click **More info → Run anyway**. To remove the warning
permanently you need a **code-signing certificate** (paid, ~$100–400/yr) and sign
both `DeveloperTracker.exe` and the setup with `signtool`. Optional, but expected
for a public product.

---

## Notes / limits of this first build

- **Antivirus false positives:** PyInstaller apps sometimes get flagged. Code
  signing + submitting to vendors fixes it.
- **Auto-update:** not included. New version = rebuild + re-upload; users
  re-run the new setup (Inno upgrades in place via the `AppId`).
- **User data location:** the app currently writes some runtime files
  (remember-me, screenshots) next to the program. Under Program Files that path
  is read-only, so I recommend a small follow-up change to write user data to
  `%APPDATA%\Developer Tracker` instead. Say the word and I'll do it.

---

## Files in this build kit
| File | Purpose |
|------|---------|
| `tracker.spec` | PyInstaller build recipe (deps, bundled `.env`, windowed) |
| `build_exe.bat` | One-click: install deps + build the `.exe` |
| `installer.iss` | Inno Setup script → makes `Setup.exe` |
| `BUILD_EXE.md` | This guide |
