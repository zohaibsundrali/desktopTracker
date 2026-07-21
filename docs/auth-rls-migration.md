# Supabase Auth + RLS migration (for public distribution)

## The problem this fixes
The app used **custom auth**: it read the `developers` table with an API key and
compared **plaintext passwords**. To distribute publicly, the app must ship the
**anon** key — and the anon key is only safe if **Row Level Security (RLS)**
isolates each user's data. Real RLS needs **Supabase Auth** so `auth.uid()` is
set on every request. This migration moves us there.

## Model: admin-provisioned
- Employees are created in **Supabase Auth** by an **admin** (never self-signup).
- Each `developers` profile row uses `id = auth.users.id`.
- All data tables already store `user_id` / `developer_id = developers.id`, so
  they automatically equal `auth.uid()` → RLS "own rows only" just works.

## Run order (do NOT skip the order)

| # | Step | Breaks the app? |
|---|------|-----------------|
| 1 | Run `migrations/004_supabase_auth_rls.sql` in the Supabase SQL editor | ❌ No — the app still uses service_role, which bypasses RLS |
| 2 | Create users in Auth: `python admin_create_user.py ...` (or the optional SQL backfill block in 004) | ❌ No |
| 3 | Switch `auth_manager.py` to Supabase Auth — ✅ **DONE (implemented)** | ⚠️ This is the switch |
| 3b | Run `migrations/005_storage_rls.sql` (screenshots bucket RLS) | ❌ No |
| 4 | In `.env`, set `SUPABASE_KEY` = **anon** key | — |
| 5 | Test: login + a full tracked session; confirm rows appear and users can't see each other's data | — |
| 6 | Run the final `alter table ... drop column password;` block in 004 | ❌ No |

Because step 1 is safe while the app is still on service_role, you can apply RLS
today and flip the app over (steps 3–4) whenever you're ready.

## Step 3 — the `auth_manager.py` change — ✅ IMPLEMENTED
`login()` now authenticates through Supabase Auth and the user's JWT is attached
to **every** Supabase client in the app (not just auth_manager) so RLS applies to
all inserts. How it fits together:

- **`supabase_session.py`** (new) — a small module that holds the signed-in
  user's access/refresh tokens and authorizes every registered client. Each
  module that creates a client (`timer_tracker`, `app_monitor`, `mouse_tracker`,
  `screenshot_capture`, `auth_manager`) now calls `supabase_session.register()`
  right after `create_client()`. `keyboard_tracker` reuses the timer's client.
- **`auth_manager.login()`** → `supabase.auth.sign_in_with_password(...)`, then
  `supabase_session.set_tokens(access, refresh)` authorizes all clients, then it
  loads the profile from `developers` (RLS returns only the user's own row).
- **`auth_manager.logout()`** → `supabase.auth.sign_out()` + `supabase_session.clear()`.
- **`register_user()`** is disabled in the app (admin-only via `admin_create_user.py`).

> ⚠️ **Token expiry over long sessions.** Supabase JWTs expire (default 1 hour).
> A single tracked shift can run longer, after which inserts would start failing.
> Fix: in the Supabase dashboard → **Authentication → Sessions**, raise the JWT
> **access-token expiry** to cover a workday (e.g. 8–12h). The refresh token is
> stored, so a future auto-refresh can be wired in if you prefer short JWTs —
> say the word.

## Supabase Storage (screenshots) — ✅ handled by migration 005
Screenshot **image files** live in the `screenshots` Storage bucket, which has
its **own** RLS on `storage.objects`. The app now uploads each image under a
per-user folder named after the user's id (= `auth.uid()`):

```
screenshots/<auth.uid()>/<filename>.jpg
```

`migrations/005_storage_rls.sql` adds SELECT/INSERT/UPDATE/DELETE policies scoping
each user to their own folder, and marks the bucket private.

> If the bucket is private, `get_public_url()` links only work with a token. To
> display images in a dashboard, switch to **signed URLs** (`create_signed_url`).
> Tell me if you want that wired into `screenshot_capture.py`.

## Files in this migration
| File | Purpose |
|------|---------|
| `migrations/004_supabase_auth_rls.sql` | Enable RLS + per-user policies on all 9 tables; optional user backfill; final drop-password |
| `migrations/005_storage_rls.sql` | RLS for the screenshots Storage bucket (per-user folders) |
| `auth_manager.py` | ✅ Rewritten to use Supabase Auth (sign-in, sign-out, admin-only accounts) |
| `supabase_session.py` | ✅ New — keeps every Supabase client authorized with the user's JWT |
| `admin_create_user.py` | Admin tool: create an employee in Auth + matching profile row (service_role, never shipped) |
| `.env.example` | Reminds you to use the anon key in distributed builds |
| `docs/auth-rls-migration.md` | This guide |
