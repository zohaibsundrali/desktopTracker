# Organization screenshot policy

Administrators control screenshots through the web organization settings. The desktop app reads `get_screenshot_policy()` for the current login and organization; employees cannot change the policy locally. The RPC returns `organization_id`, `enabled`, and `interval_seconds` (integer 60–3600). The database default is enabled with a 60-second interval.

The desktop displays the policy state and interval beside screenshot synchronization. Pause stops all tracking, including screenshots and screenshot uploads; Resume continues under the current admin policy. Stop and login changes preserve the existing privacy guards.

The worker checks policy before capturing, before committing a newly captured image, and before each upload/finalization network phase. While running, policy is refreshed at least every 30 seconds between captures; disabled or unavailable policy is retried after 30 seconds. Capture and upload are held if the RPC fails, returns malformed data, or identifies a different organization. This deliberately also holds new screenshots while offline rather than trusting an old permission indefinitely. The last policy status is a cached snapshot; a request already started cannot be recalled.

Existing queued screenshots are retained when policy is disabled or unavailable. They can resume only after a successful enabled policy check and while tracking is active. No local age-based deletion or employee override is introduced. Backend rules remain authoritative against modified clients.

Deploy the corresponding website policy migration and web release before distributing this desktop version. Without the RPC, screenshots remain held and the desktop shows policy unavailable. Existing time/activity tracking continues subject to its own authorization checks.

Verification: offline HTTP and OS-capture mocks cover disabled policy, malformed responses, wrong organization, account switch during lookup, network failure after an enabled response, interval bounds, a policy change between image capture and local persistence, and a policy change between Storage and metadata requests. Live Windows capture and production Supabase behavior require release smoke testing.
