-- ============================================================================
-- Migration 005: Row Level Security for the screenshots Storage bucket
-- ============================================================================
--
-- Screenshot IMAGE FILES live in Supabase Storage (bucket "screenshots"), which
-- has its own RLS on storage.objects — separate from the screenshots table.
--
-- The app now uploads each image under a per-user folder named after the user's
-- id (= auth.uid()), i.e.  screenshots/<auth.uid()>/<filename>.jpg
-- (see screenshot_capture.py). These policies scope every user to their own
-- folder.
--
-- Run this AFTER migration 004 and after the app is on Supabase Auth + anon key.
-- Adjust the bucket name below if yours differs.
-- ============================================================================

-- Make the bucket private (RLS-governed). Skip if it must stay public.
update storage.buckets set public = false where id = 'screenshots';

alter table storage.objects enable row level security;

drop policy if exists screenshots_read_own on storage.objects;
create policy screenshots_read_own on storage.objects
  for select to authenticated
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists screenshots_insert_own on storage.objects;
create policy screenshots_insert_own on storage.objects
  for insert to authenticated
  with check (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists screenshots_update_own on storage.objects;
create policy screenshots_update_own on storage.objects
  for update to authenticated
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  )
  with check (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

drop policy if exists screenshots_delete_own on storage.objects;
create policy screenshots_delete_own on storage.objects
  for delete to authenticated
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = auth.uid()::text
  );

-- NOTE: if the bucket is private, get_public_url() returns a URL that only works
-- with a valid token. To show images in a dashboard, use signed URLs
-- (create_signed_url) instead — tell me if you need that wired in.
