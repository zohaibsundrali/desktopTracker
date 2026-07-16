-- Migration 001: create login_preferences
--
-- Used by auth_manager.py (save_remember_me / get_remembered_email) for the
-- cross-device "Remember me" feature. Stores EMAIL ONLY — never passwords.
-- The table is currently missing in the database, so those calls silently
-- no-op (errors are swallowed). Creating it enables remember-me to persist.

create table if not exists public.login_preferences (
    email       text        primary key,
    remember_me boolean     not null default false,
    updated_at  timestamptz not null default now()
);

-- Enable Row Level Security. The desktop app connects with the service_role
-- key, which bypasses RLS, so it keeps working; anonymous/public access is
-- denied by default. Add explicit policies later if a non-service client
-- (e.g. the web dashboard using the anon key) needs access.
alter table public.login_preferences enable row level security;
