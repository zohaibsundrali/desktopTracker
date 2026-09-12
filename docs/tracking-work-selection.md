# Desktop project and task selection

Before Start, choose a project and optionally one of its tasks. General tracking preserves unattributed sessions. The list includes only work returned by the current identity's authorized backend function; matching names include IDs so users can distinguish them. Changing project resets the task. Stop the session before changing work; Pause keeps the existing work selection.

Loading runs outside the UI thread. If the service is unavailable, choose Refresh projects or start General tracking. Selected work is revalidated before start; stale or revoked assignments must fail rather than silently attributing time elsewhere. Options from an older request, logged-out window, or another identity are ignored.

Install the corresponding backend tracking-work migration before distributing this desktop build. Existing General tracking remains usable when the selection service is unavailable, subject to the existing authentication and tracking policy checks. Test two assigned projects, duplicate names, project-only and task attribution, pause/resume, stop/restart, revoked assignment, offline queue replay, and account switching on a supported desktop OS. Verify selected IDs on persisted sessions. This release does not convert tracked sessions into approved or billable timesheets automatically.
