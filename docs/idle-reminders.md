# Idle reminder controls

The administrator controls enablement and threshold (60–3600 seconds), initiallydisabled/300 seconds. Employees see status and can Continue tracking or Pause when reminded. Continue dismisses until new input; Pause uses existing tracked-break behavior. There is no automatic pause or retroactive deletion/deduction.

Both keyboard and mouse observations must be healthy. Mouse movement, stationary clicks and scroll events reset its monotonic activity clock. Missing sensors or policy do not prove inactivity; no reminder is shown and unknown gaps are excluded. The policy is bound to the current identity, checked in a background worker and refreshed every30 seconds. UI getters do no network work.

Apply web migration20260912083144_production_organization_idle_reminder_policy.sql before updating the desktop package. Verify the prior recorded-break migration also ran before using Pause on the updated app. Rebuild with idle_reminder included. Test the Windows listener permission/health checks, policy refresh, Continue, input reset, Pause/Resume, logout/revocation and missing-policy behavior on a staging device. Reading and meetings can legitimately involve no input.
