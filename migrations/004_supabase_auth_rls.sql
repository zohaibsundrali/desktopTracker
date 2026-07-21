-- ============================================================================
-- Migration 004: Supabase Auth + Row Level Security (per-user data isolation)
-- ============================================================================
--
-- WHY: The desktop app is about to be distributed publicly. A public build must
-- ship the *anon* key (never service_role). The anon key is only safe if RLS
-- isolates each user's data, and real RLS requires Supabase Auth so that
-- auth.uid() is populated on every request.
--
-- MODEL: Admin-provisioned. Employees are created in Supabase Auth by an admin
-- (see admin_create_user.py). The desktop app only SIGNS IN. Each `developers`
-- profile row uses id = the user's auth.users.id, so every data table (which
-- already stores user_id / developer_id = developers.id) automatically matches
-- auth.uid().
--
-- SAFE TO RUN NOW: while the app still uses the service_role key it BYPASSES
-- RLS, so enabling RLS here does not break the running app. Isolation takes
-- effect once the app switches to Supabase Auth + the anon key.
--
-- RUN ORDER:
--   1. This migration (RLS + policies)            <- you are here
--   2. Backfill / create users in Auth            (admin_create_user.py or the
--                                                   optional backfill block below)
--   3. Switch auth_manager.py to Supabase Auth     (code change - next step)
--   4. Switch .env SUPABASE_KEY to the anon key
--   5. Test login + a full session, then run the final "DROP password" block
-- ============================================================================

-- pgcrypto lives in the `extensions` schema on Supabase (needed for crypt()).
create extension if not exists pgcrypto with schema extensions;

-- Supabase Auth now owns passwords. Make the legacy plaintext column optional so
-- admin_create_user.py can insert profile rows WITHOUT a password (the column is
-- dropped entirely in the FINAL block once every user can sign in via Auth).
alter table public.developers alter column password drop not null;

-- Helper note: every policy casts both sides to text so it works whether the
-- id column is typed uuid or text (this schema mixes them).

-- ---------------------------------------------------------------------------
-- developers  (profile). id = auth.users.id. A user may read/update ONLY their
-- own profile. Creating/deleting profiles is admin-only (service_role bypasses
-- RLS, so no policy is granted to `authenticated` for INSERT/DELETE).
-- ---------------------------------------------------------------------------
alter table public.developers enable row level security;

drop policy if exists dev_select_own on public.developers;
create policy dev_select_own on public.developers
  for select to authenticated
  using (id::text = auth.uid()::text);

drop policy if exists dev_update_own on public.developers;
create policy dev_update_own on public.developers
  for update to authenticated
  using (id::text = auth.uid()::text)
  with check (id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- productivity_sessions  (user_id = auth.uid())
-- ---------------------------------------------------------------------------
alter table public.productivity_sessions enable row level security;

drop policy if exists ps_select_own on public.productivity_sessions;
create policy ps_select_own on public.productivity_sessions
  for select to authenticated
  using (user_id::text = auth.uid()::text);

drop policy if exists ps_insert_own on public.productivity_sessions;
create policy ps_insert_own on public.productivity_sessions
  for insert to authenticated
  with check (user_id::text = auth.uid()::text);

drop policy if exists ps_update_own on public.productivity_sessions;
create policy ps_update_own on public.productivity_sessions
  for update to authenticated
  using (user_id::text = auth.uid()::text)
  with check (user_id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- app_usage  (owned by user_email; this table's session_id is generated
-- independently by AppMonitor and does NOT match productivity_sessions, so we
-- scope by the signed-in user's email. Rows are UPSERTED -> needs INSERT+UPDATE.
-- Compared case-insensitively so a differently-cased login still matches.)
-- ---------------------------------------------------------------------------
alter table public.app_usage enable row level security;

drop policy if exists au_select_own on public.app_usage;
create policy au_select_own on public.app_usage
  for select to authenticated
  using (lower(user_email) = lower(auth.jwt() ->> 'email'));

drop policy if exists au_insert_own on public.app_usage;
create policy au_insert_own on public.app_usage
  for insert to authenticated
  with check (lower(user_email) = lower(auth.jwt() ->> 'email'));

drop policy if exists au_update_own on public.app_usage;
create policy au_update_own on public.app_usage
  for update to authenticated
  using (lower(user_email) = lower(auth.jwt() ->> 'email'))
  with check (lower(user_email) = lower(auth.jwt() ->> 'email'));

-- ---------------------------------------------------------------------------
-- keyboard_stats  (developer_id = auth.uid())
-- ---------------------------------------------------------------------------
alter table public.keyboard_stats enable row level security;

drop policy if exists ks_select_own on public.keyboard_stats;
create policy ks_select_own on public.keyboard_stats
  for select to authenticated
  using (developer_id::text = auth.uid()::text);

drop policy if exists ks_insert_own on public.keyboard_stats;
create policy ks_insert_own on public.keyboard_stats
  for insert to authenticated
  with check (developer_id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- mouse_activities  (developer_id = auth.uid())
-- ---------------------------------------------------------------------------
alter table public.mouse_activities enable row level security;

drop policy if exists ma_select_own on public.mouse_activities;
create policy ma_select_own on public.mouse_activities
  for select to authenticated
  using (developer_id::text = auth.uid()::text);

drop policy if exists ma_insert_own on public.mouse_activities;
create policy ma_insert_own on public.mouse_activities
  for insert to authenticated
  with check (developer_id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- screenshots  (developer_id = auth.uid())
-- NOTE: image FILES live in Supabase Storage. Storage has its OWN RLS on
-- storage.objects - see docs/auth-rls-migration.md for the bucket policy.
-- ---------------------------------------------------------------------------
alter table public.screenshots enable row level security;

drop policy if exists sc_select_own on public.screenshots;
create policy sc_select_own on public.screenshots
  for select to authenticated
  using (developer_id::text = auth.uid()::text);

drop policy if exists sc_insert_own on public.screenshots;
create policy sc_insert_own on public.screenshots
  for insert to authenticated
  with check (developer_id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- browser_usage  (owned by user_email, same reasoning as app_usage; its
-- session_id is AppMonitor-generated and does not match productivity_sessions.
-- Upserted -> needs INSERT+UPDATE. Case-insensitive email match.)
-- ---------------------------------------------------------------------------
alter table public.browser_usage enable row level security;

drop policy if exists bu_select_own on public.browser_usage;
create policy bu_select_own on public.browser_usage
  for select to authenticated
  using (lower(user_email) = lower(auth.jwt() ->> 'email'));

drop policy if exists bu_insert_own on public.browser_usage;
create policy bu_insert_own on public.browser_usage
  for insert to authenticated
  with check (lower(user_email) = lower(auth.jwt() ->> 'email'));

drop policy if exists bu_update_own on public.browser_usage;
create policy bu_update_own on public.browser_usage
  for update to authenticated
  using (lower(user_email) = lower(auth.jwt() ->> 'email'))
  with check (lower(user_email) = lower(auth.jwt() ->> 'email'));

-- ---------------------------------------------------------------------------
-- developer_logins  (developer_id = auth.uid())
-- ---------------------------------------------------------------------------
alter table public.developer_logins enable row level security;

drop policy if exists dl_select_own on public.developer_logins;
create policy dl_select_own on public.developer_logins
  for select to authenticated
  using (developer_id::text = auth.uid()::text);

drop policy if exists dl_insert_own on public.developer_logins;
create policy dl_insert_own on public.developer_logins
  for insert to authenticated
  with check (developer_id::text = auth.uid()::text);

-- ---------------------------------------------------------------------------
-- login_preferences  (email keyed). With Supabase Auth, remember-me is local
-- only, but we still lock this table to the signed-in user's own email.
-- ---------------------------------------------------------------------------
alter table public.login_preferences enable row level security;

drop policy if exists lp_select_own on public.login_preferences;
create policy lp_select_own on public.login_preferences
  for select to authenticated
  using (lower(email) = lower(auth.jwt() ->> 'email'));

drop policy if exists lp_upsert_own on public.login_preferences;
create policy lp_upsert_own on public.login_preferences
  for insert to authenticated
  with check (lower(email) = lower(auth.jwt() ->> 'email'));

drop policy if exists lp_update_own on public.login_preferences;
create policy lp_update_own on public.login_preferences
  for update to authenticated
  using (email = (auth.jwt() ->> 'email'))
  with check (lower(email) = lower(auth.jwt() ->> 'email'));

-- ============================================================================
-- OPTIONAL: backfill existing developers into Supabase Auth (preserving ids)
-- ----------------------------------------------------------------------------
-- Run this ONLY if you want to keep the existing test users + their historical
-- data. It inserts each developer into auth.users with the SAME id, migrating
-- the plaintext password to a bcrypt hash. Direct auth.users insertion is
-- version-sensitive; test on ONE user first. The supported alternative is to
-- create users via admin_create_user.py (Auth Admin API).
--
-- Uncomment to use:
--
-- insert into auth.users (
--     instance_id, id, aud, role, email, encrypted_password,
--     email_confirmed_at, created_at, updated_at,
--     raw_app_meta_data, raw_user_meta_data
-- )
-- select
--     '00000000-0000-0000-0000-000000000000',
--     d.id,
--     'authenticated',
--     'authenticated',
--     d.email,
--     extensions.crypt(d.password, extensions.gen_salt('bf')),
--     now(), now(), now(),
--     '{"provider":"email","providers":["email"]}'::jsonb,
--     jsonb_build_object('name', d.name, 'company', d.company)
-- from public.developers d
-- where d.password is not null
--   and not exists (select 1 from auth.users u where u.id = d.id);
--
-- insert into auth.identities (
--     provider_id, user_id, identity_data, provider, created_at, updated_at
-- )
-- select
--     d.id::text, d.id,
--     jsonb_build_object('sub', d.id::text, 'email', d.email),
--     'email', now(), now()
-- from public.developers d
-- where not exists (
--     select 1 from auth.identities i
--     where i.user_id = d.id and i.provider = 'email');
-- ============================================================================

-- ============================================================================
-- FINAL (run only AFTER auth works end-to-end): remove plaintext passwords.
-- Once every user can sign in via Supabase Auth, the plaintext column is a pure
-- liability. Drop it.
--
--   alter table public.developers drop column if exists password;
-- ============================================================================
