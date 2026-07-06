# Changelog

## 2.2.19 (2026-07-06)

### Framework Contract Call-off

- **FC call-off SC creation** — Users can create call-off SCs linked to a framework contract PO via the new `calloff_po_id` field. A PO(FC) selector dialog shows available FC POs with remaining budget.
- **FC budget tracking** — `compute_po_fc_budget` and `compute_sc_fc_budget` functions track consumed vs. remaining budget across call-off SCs, with null-contract-value guards.
- **FC PO behavior guards** — FC POs cannot be finished, updated, recalled, or deleted while call-off SCs exist. GR creation under FC POs is blocked.
- **FC badges and filters** — SC and PO lists show FC/Call-off badges and filters. PO detail view renders conditionally for FC vs. regular POs.
- **SC budget summary card** — Detail views show call-off parent context and budget consumption summary via `ScBudgetCard` / `PoBudgetCard` components.
- **Import/Export** — `calloff_po_id` column added to SC import/export templates. FC PO budget included in notification thresholds and monthly summaries.

### GR Annual Report Export

- **API endpoint** — `get_gr_annual_report` returns aggregated annual report data for GR records.
- **Query layer** — `get_annual_report_data` query with proper aggregation and filtering.
- **Frontend** — Annual report export button on GR List view with dialog for parameter selection. Consolidated `useExport()` composable.

### Last Delivery Cascade

- **Auto-finish PO** — When a GR with `last_delivery` flag is finished, the linked PO is automatically finished in the same transaction.
- **Cascade confirmation** — UI prompts user for confirmation when finishing a GR that will cascade-finish its parent PO, with `confirmCascade` parameter flowing through the bridge.
- **Validation** — `last_delivery` value validation and uniqueness constraint per PO.

### Denied SC/GR WorkBench

- **WorkBench top section** — Denied SCs and GRs are now displayed in a dedicated section at the top of the WorkBench, with `home.denied` i18n key.
- **Visibility tests** — Unit tests for denied SC/GR visibility in workbench data.

### Import NO-based Linking

- **SC/PO/GR import** — All import flows now link records by NO (e.g. `po_no`) instead of database IDs, making templates human-readable.
- **New columns** — `vendor_id`, `asset`, `asset_nums`, `active_date` columns supported in import templates.
- **Multi-format date parsing** — `parse_date` utility added to `import_service` for flexible date input formats.
- **Process summary** — Import now shows a timeline of processed rows with `updated_at` tracking.
- **Frontend** — Import column labels updated to NO-based references; ID columns hidden.

### Email Improvements

- **Sender configuration** — System settings UI for configuring sender email, backed by `sender_email_config` API and `SendUsingAccount` Outlook support.
- **Greeting line** — Operational emails now include a personalized greeting line.

### Export Optimization

- **Cascade export** — SC export cascades to linked POs and GRs with multi-sheet workbook and summary statistics sheet.
- **Import preview dialog** — Import flow now shows a preview dialog before committing changes.

### Detail View Restructuring

- **ProcessSummaryCard** — Shared component showing process timeline across detail views.
- **PoBudgetCard** — PO detail view shows budget summary breakdown.
- **Conditional rendering** — PO detail adapts rendering for FC vs. regular POs.
- **Workbench layout** — SC workbench uses 5-column layout with FC call-off support.

### Tests

- **Service tests** — Comprehensive unit tests for `sc_service` (create, submit, confirm, approve, deny, finish, recall, delete, transfer, vendors, call-off).
- **GR tests** — Unit tests for `gr_service` (create, submit, confirm, approve, deny, finish, recall, delete, validation).
- **PO tests** — Unit tests for `po_service` (create, submit, finish, delete, recall, non-FC variants).
- **Integration tests** — FC call-off flow, mixed-status call-off, denied budget release.
- **Migration tests** — Updated for v31 (calloff_po_id), v32 (finished_by), v33 (Last Delivery).

### Bug Fixes

- **Draft PO creation under approved SC** — Previously blocked; now allowed.
- **FC SC/PO exclusion from GR dropdown** — FC-related entities no longer appear in GR creation dropdown.
- **`sc_request_type` propagation** — Fixed missing propagation to PO objects from SC detail.
- **Notification console window residue** — Notification exe compiled without console window to prevent `OpenConsole` residue.

---

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
