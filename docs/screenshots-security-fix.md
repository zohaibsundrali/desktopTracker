# Screenshots Security Fix — Private Bucket + Signed URLs

**Problem:** the `screenshots` Storage bucket is **public**. Every screenshot's
`public_url` is readable by anyone with the link — no login required. Verified:
an unauthenticated request to a screenshot returns HTTP 200.

**Goal:** make the bucket **private** and serve screenshots through short-lived
**signed URLs** generated on demand. The desktop app already stores
`storage_path` on every row, so the dashboard has everything it needs.

> ⚠️ **Roll out in this exact order** or the dashboard breaks:
> 1. Deploy the dashboard change below (works while the bucket is still public).
> 2. Flip the bucket to private.
> 3. Apply RLS + desktop cleanup.

---

## Step 1 — Dashboard change (the web app that shows screenshots)

Today the dashboard reads the `public_url` column directly. Change it to
generate a signed URL from `storage_path` when a screenshot is displayed.

### Supabase JS client (v2)

```js
import { createClient } from '@supabase/supabase-js'

// Use the ANON key on the dashboard, NOT service_role.
const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY)

/**
 * Turn a stored storage_path into a temporary viewable URL.
 * @param {string} storagePath  e.g. "zohaib6511/screenshot_2026...jpg"
 * @param {number} expiresIn    seconds the link stays valid (default 60s)
 */
async function getScreenshotUrl(storagePath, expiresIn = 60) {
  const { data, error } = await supabase
    .storage
    .from('screenshots')
    .createSignedUrl(storagePath, expiresIn)

  if (error) {
    console.error('signed url failed:', error.message)
    return null
  }
  return data.signedUrl
}
```

### Using it when rendering a list

```js
// rows = await supabase.from('screenshots').select('id, storage_path, timestamp, developer_email')...
for (const row of rows) {
  const url = await getScreenshotUrl(row.storage_path, 60)
  // <img src={url} /> — regenerate when the user reopens; links expire after `expiresIn`.
}
```

Batch variant (fewer round-trips):

```js
const paths = rows.map(r => r.storage_path)
const { data } = await supabase.storage
  .from('screenshots')
  .createSignedUrls(paths, 60)   // returns [{ path, signedUrl, error }]
```

**Key points**
- Stop reading `public_url` from the DB — it stops working once the bucket is private.
- Generate the signed URL at view time; don't store it. Short `expiresIn` (30–120s)
  is fine because it's created right before the `<img>` renders.
- The signed URL only works for someone who already has a valid session/key —
  combined with the RLS below, only authorised viewers can create one.

### REST equivalent (if the dashboard isn't JS)

```
POST {SUPABASE_URL}/storage/v1/object/sign/screenshots/{storage_path}
Headers: apikey: <anon>, Authorization: Bearer <session-or-anon>, Content-Type: application/json
Body:    { "expiresIn": 60 }
Response:{ "signedURL": "/object/sign/screenshots/..." }
View at: {SUPABASE_URL}/storage/v1{signedURL}
```

---

## Step 2 — Flip the bucket to private

Done once Step 1 is deployed. Either in the Supabase dashboard
(Storage → screenshots → Settings → make private), or the API call I can run
for you from the project's existing `.env` connection.

After this, `object/public/...` URLs return 400/403; only signed URLs work.

---

## Step 3 — RLS policies (run in Supabase SQL editor)

The `screenshots` **table** and the storage objects both need Row Level Security
so the anon key can't read everything. Adjust the role/claim checks to match how
your dashboard authenticates (Supabase Auth assumed here).

```sql
-- Metadata table
alter table public.screenshots enable row level security;

-- A developer can insert/read only their own rows.
-- Assumes screenshots.developer_id matches the authenticated user id.
create policy "own rows - select"
  on public.screenshots for select
  using ( auth.uid() = developer_id );

create policy "own rows - insert"
  on public.screenshots for insert
  with check ( auth.uid() = developer_id );

-- Managers/admins can read all rows (example: a role flag on a profiles table).
-- create policy "admins read all"
--   on public.screenshots for select
--   using ( exists (select 1 from profiles p where p.id = auth.uid() and p.is_admin) );
```

```sql
-- Storage objects in the 'screenshots' bucket
create policy "screenshots - owner read"
  on storage.objects for select
  using (
    bucket_id = 'screenshots'
    and (storage.foldername(name))[1] = (auth.jwt() ->> 'username')  -- adjust to your path scheme
  );

create policy "screenshots - owner upload"
  on storage.objects for insert
  with check ( bucket_id = 'screenshots' );
```

> These are a starting point — the exact predicates depend on your auth model
> (who is a "manager", how the developer id maps to `auth.uid()`, etc.).
> Test with a non-admin account before trusting them.

---

## Step 4 — Desktop app cleanup (this repo)

Once the bucket is private, `get_public_url()` in `screenshot_capture.py`
(around line 288) returns a URL that no longer works, so storing it is pointless.

Change the upload to stop fetching/storing `public_url` and rely on
`storage_path` (already stored). The dashboard builds the viewable URL itself.
I'll make this edit in `screenshot_capture.py` as the final step.

---

## Current status

- [x] Verified the leak (unauthenticated screenshot access returns 200)
- [x] Verified signed URLs work on the real data
- [ ] Step 1 — dashboard updated to signed URLs
- [ ] Step 2 — bucket set to private
- [ ] Step 3 — RLS policies applied
- [ ] Step 4 — desktop app stops storing public_url
