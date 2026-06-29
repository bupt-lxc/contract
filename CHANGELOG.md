# Changelog

## 2.2.0 (2026-06-29)

### Email Notification Overhaul

- **Auto-open Outlook drafts on status transitions** — After every SC/PO/GR status transition (submit, approve, deny, confirm, revoke, create, finish, cancel), an Outlook draft email is automatically opened via `mail.Save()` + `mail.Display()`. This replaces the previous behavior where the notification poll script would silently create or send emails. Best-effort: failures are logged but never block the operation.
- **Poll script skips status_change events** — `fetch_pending()` and `fetch_failed()` now exclude `event_type = 'status_change'`. The notification poll script (`python -m sc_gr_app.notification`) only processes reminders: thresholds, custom schedules, and monthly summaries.
- **Manual Preview & Send for any non-sent entry** — Email logs page now shows the Preview & Send button for all pending and failed queue entries, not just pending status_change. This allows manual retry when Outlook is offline or a previous send failed.
- **Fix daily email sequence off-by-one** — Subject numbering changed from `COUNT(*) + 1` to `COUNT(*)`, fixing the issue where the first email of the day was `-002` instead of `-001`.

### SC Email Template Improvements

- **Removed unnecessary fields** — Created By, Approved By, Approved At, Confirmed At, Pending Total, Pending Total Incl Tax, and Child POs are no longer shown in SC notification emails.
- **Vendor Info section** — SC emails now include a third table listing all linked vendors with Vendor ID, Vendor Name, Service Scope, Contact, Phone, and Email.
- **Manager_confirm status label** — Displays as "To be confirm" in email Detail Info instead of the raw `manager_confirm` value.

### Bug Fixes

- **Empty admin_recipients no longer silently drops notifications** — When no admin recipients are configured, CC recipients (typically the requester) are now promoted to TO instead of the notification being silently skipped.
- **10 incorrect i18n key references** — Fixed ScDetailView.vue to use correct keys (`scUpdated`, `submitConfirm`, `scSubmitted`, `approveConfirm`, `scApproved`, `denyConfirm`, `scDenied`, `closePrompt`, `closeTitle`, `scClosed`).
- **Missing i18n keys** — Added `gr.vendorId`, `gr.pendingDate`, `gr.approvedDate`, `common.saved` to both en-US and zh-CN locale files.
- **el-checkbox deprecation warning** — Changed `:label` to `:value` on `<el-checkbox>` elements to match Element Plus 2.11+ API.
