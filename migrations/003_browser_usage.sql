-- Migration 003: per-website browser usage
--
-- Stores how much time was spent on each site inside a browser (ChatGPT,
-- Claude, Gemini, YouTube, GitHub, ...). Populated by app_monitor.py via
-- site_detector.py (tab-title detection + optional address-bar URL fallback).
-- One row per (session_id, site); upserted as time accumulates.

create table if not exists public.browser_usage (
    id               bigserial   primary key,
    session_id       text        not null,
    user_login       text,
    user_email       text,
    site             text        not null,
    duration_seconds numeric(10, 2),
    duration_minutes numeric(10, 4),
    first_seen       timestamptz,
    last_seen        timestamptz,
    created_at       timestamptz default now(),
    unique (session_id, site)
);

alter table public.browser_usage enable row level security;

create index if not exists idx_browser_usage_session on public.browser_usage (session_id);
create index if not exists idx_browser_usage_site    on public.browser_usage (site);
