-- Migration 002: make the daily login limit race-safe
--
-- Problem (TOCTOU race in auth_manager.py):
--   login() does  count = get_daily_login_count(dev)   -- read
--                 if count < 2: record_successful_login(dev)  -- then insert
--   Two logins at the same instant both read count=1, both insert -> 3/day.
--
-- Fix: enforce the limit inside the database with a BEFORE INSERT trigger that
-- takes a per-(developer, day) transaction-level advisory lock. Concurrent
-- inserts for the same developer+date are serialized, so the count-then-insert
-- becomes atomic. No application code change is required — the app just inserts,
-- and an over-limit insert is rejected (auth_manager already handles the error).

create or replace function public.enforce_daily_login_limit()
returns trigger
language plpgsql
as $$
declare
    existing_count int;
begin
    -- Serialize concurrent inserts for the same developer + login_date.
    -- The lock is held until the transaction ends, so the following count
    -- sees every already-committed row for this developer+day.
    perform pg_advisory_xact_lock(
        hashtext(NEW.developer_id::text || ':' || NEW.login_date::text)
    );

    select count(*) into existing_count
    from public.developer_logins
    where developer_id = NEW.developer_id
      and login_date   = NEW.login_date;

    if existing_count >= 2 then
        raise exception
            'Daily login limit reached for developer % on %',
            NEW.developer_id, NEW.login_date
            using errcode = 'check_violation';
    end if;

    return NEW;
end;
$$;

drop trigger if exists trg_enforce_daily_login_limit on public.developer_logins;

create trigger trg_enforce_daily_login_limit
    before insert on public.developer_logins
    for each row
    execute function public.enforce_daily_login_limit();
