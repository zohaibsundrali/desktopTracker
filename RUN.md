# Developer Tracker — Run & Verify Guide

A Hubstaff-style time & activity tracker. It records, per work session:

- **Time tracking** — start / pause / stop timer
- **Activity level** — a productivity score from real keyboard + mouse activity (idle time excluded)
- **Mouse activity** — movement, clicks, active vs idle %
- **Keyboard activity** — key counts, words-per-minute, active vs idle %
- **Screenshots** — periodic full-screen captures (with the active app)
- **App / window tracking** — which apps were used and for how long

All data uploads to your Supabase project.

> ⚠️ Full capture works on **Windows** only (it uses Win32 APIs for the
> foreground window). Run it on the developer's Windows machine.

---

## 1. Install

```bat
cd developer-tracker
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
pip install pywin32          :: Windows-only: needed for app/window tracking
```

## 2. Configure

Copy the template and fill in your Supabase details:

```bat
copy .env.example .env
```

Edit `.env`:

```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_KEY=<your-anon-or-service-key>
```

## 3. Self-test (confirm every feature is ready)

```bat
python selftest.py
```

You want **all checks `[ OK ]`**. It verifies Python, dependencies, the
Supabase connection, and the low-level capabilities each feature needs
(screenshot grab, mouse read, input listeners, window detection).
Fix any `[FAIL]` line before continuing.

## 4. Run the app

```bat
python main.py
```

1. Log in with a developer account (row in the `developers` table).
2. On the dashboard, press **Start**.
3. Work normally for a few minutes (type, move the mouse, switch apps).
4. Press **Stop** to finalize the session.

## 5. Verify data reached Supabase

After a session, these tables should have **new rows** (check the Supabase
Table editor, newest first):

| Feature            | Table                    |
|--------------------|--------------------------|
| Time + activity %  | `productivity_sessions`  |
| Mouse activity     | `mouse_activities`       |
| Keyboard activity  | `keyboard_stats`         |
| Screenshots (meta) | `screenshots`            |
| Screenshot images  | Storage bucket `screenshots` |
| App / window usage | `app_usage`              |

If new rows appear in each, **all features are working**.

---

## Notes

- **Screenshots** are taken on a randomized interval (default every 60–120s).
  Set `SCREENSHOTS_ENABLED=false` in `.env` to disable them.
- **Window titles** are sanitized before upload — URL query strings, tokens,
  and emails are redacted so secrets are not stored.
- **Offline safety** — if a session fails to upload (network drop), it is
  queued locally in `.pending_sessions.jsonl` and retried on next launch.
- If the app can't start, re-run `python selftest.py` and fix the failing checks.
