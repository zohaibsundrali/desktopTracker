# DevTrack feature implementation backlog

Functional benchmark reviewed 12 September 2026: https://hubstaff.com/features . This is a phased DevTrack implementation plan, not a statement that feature parity or production readiness has been achieved. Preserve existing product architecture, UI, role authority and Free/Professional/Business/Enterprise entitlements. Product-specific plan limits must be explicitly defined before newly added features are enabled.

## Delivery order

| Phase | Scope | Existing foundation | Completion criteria |
| --- | --- | --- | --- |
| 1 | Reliable desktop time capture and offline session recovery | Desktop timer, device authentication, session upserts, local failed-session file | Pending records survive crash/restart; confirmed uploads alone are removed; replay stays bound to its original account and organization; invalid records are retained for review; duplicate replay does not create another session; offline and logout races tested. |
| 2 | Tracking controls and privacy | Start/pause controls, screenshots, app/site activity, device revocation | Explicit visible tracking state; task/project selection; permissioned capture settings; optional blur; idle-time review; work-hour controls; no capture while paused or signed out; server rejects unauthorized writes. |
| 3 | Timesheet and attendance workflows | Timesheets, approvals, attendance, leave | Complete tracked-time-to-submission-to-approval flow; audited corrections with reason; time zones, overnight periods, breaks, overtime policies and approval locking; scheduling and PTO rules explicitly configured. |
| 4 | Client costing and financial reporting | Billable hours, invoicing, project profitability and client portal | Approved time reconciles with invoices; configurable cost/bill rates; budget thresholds and alerts; scoped client reports; historical rates and corrections do not silently change issued invoices. |
| 5 | Workforce and developer analytics | Productivity, performance, capacity and reporting modules | Reconciled source data, role-scoped drilldowns, focus/utilization trends, scheduled reports, definitions and missing-data explanations. Keyboard/mouse activity never presented as an objective code-quality or employee-performance measure. |
| 6 | Tool integrations | Application APIs; complete GitHub/Jira synchronization not verified | GitHub first, then Jira and Slack; authorized organization installation, minimal scopes, signed webhooks, idempotent imports, disconnect/revocation, retries and visible sync health. Connect issues/PR reviews to tasks without treating commit count as productivity. |
| 7 | Payments and enterprise interfaces | SaaS Stripe subscription billing; employee payouts are a separate product flow | Provider-backed employee payout sandbox, approvals, reconciliation and failure recovery; scoped API tokens/webhooks; SSO and lifecycle provisioning only after provider setup and role mapping are specified. |
| 8 | Additional clients and advanced operations | Existing desktop/web clients | Browser extension, mobile apps, and field-team GPS/geofencing if required for target customers; explicit location controls; supported-OS installers, updates, signing and real-device tests. Advanced anomaly signals require validation and human review. |

## Existing release gates

Legacy identity repair remains separate and urgent: eleven reviewed staff links are not confirmed applied; five Admin profiles and one Client profile are absent, and one Owner has no matching Auth candidate. Original ownership and onboarding evidence remain required. Never reconstruct these identities by guessing missing values.

Production Stripe/email delivery, scheduler execution, retention/organization cleanup, and supported desktop OS behavior still require real integration tests. PR105 adds recovery tooling and email reliability fixes but does not complete those external checks.

## Phase 1 implementation record

Inspection found that `timer_tracker.py` truncates `.pending_sessions.jsonl` before retrying its contents. A crash between truncation and requeue can lose failed sessions. Replay also needs explicit account/organization checks rather than stamping old rows with whichever identity is signed in later. These are the first bounded implementation targets; app-usage and screenshot offline recovery remain separate work until explicitly implemented and tested.

Each delivered slice needs a tested PR, migration/install instructions where applicable, and a clear statement of external verification still pending. A backlog row is not marked complete just because a component or mock test exists.

### First delivered slice

Phase 1 session-summary recovery and dashboard sync status are implemented. Fifty offline tests pass, including the pinned Supabase SDK header isolation test and process-crash recovery. The dashboard distinguishes queued summaries, last successful sync, unavailable status and legacy records needing review. Packaged Windows and live backend verification remain release gates; phases 2–8 and non-session telemetry offline persistence are not complete.

### Screenshot recovery slice

Durable screenshot bytes, stable capture identities, phased Storage/metadata retry, current-account and pause/stop guards, plus separate dashboard screenshot-sync status are implemented in the next coordinated web/desktop release. This requires the screenshot-finalization migration before desktop rollout. Organization screenshot policy is now implemented: Admin controls enablement and interval, while employees see policy/status and can pause the whole tracker. Optional blur remains separate future work. Actual Windows/provider verification remains required.


### Project/task session attribution slice

Desktop users can select currently authorized projects and related tasks before starting a session, or leave General tracking selected. Options load asynchronously with account/request guards; project changes reset the task, and selection remains frozen while running or paused. A failed options request exposes retry and preserves General tracking. The timer revalidates selected work before start; persisted session summaries retain the selected IDs during recovery. This is attribution of tracked sessions, not automatic timesheet submission, approvals, invoicing, or billable-hour generation. Supported-OS UI and live authorization smoke tests remain required.

### Recorded break slice

Manual Pause/Resume/Stop now preserves stable break intervals and monotonic durations in the durable session checkpoint. Desktop status and web session history distinguish closed intervals from interrupted/open ones. This requires migration20260912081724_production_tracking_break_history.sql. Breaks remain excluded from tracked time; paid/unpaid classification, automatic idle deduction and idle review are separate work. Windows/hosted verification remains pending.

### Advisory idle reminder slice

Admin-controlled idle reminders and employee Continue/Pause choices are implemented with healthy dual-input detection and no automatic time deduction. Migration20260912083144_production_organization_idle_reminder_policy.sql is required. This does not complete idle-time correction/approval or payroll classification. Real Windows input-listener and hosted-policy verification remain pending.
