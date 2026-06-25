# POMP Enhancements — Design Spec

**Date:** 2026-06-25
**Status:** Draft

---

## Overview

~13 enhancements across data schema, import/export, registration, email, UI, and installer packaging. Grouped into 5 streams by dependency order.

---

## Stream A: Data & Schema Changes

### A1. SC Currency Field

- New column `currency` on `sc_records`: `TEXT NOT NULL DEFAULT 'CNY'`
- Allowed values: `CNY`, `EUR`, `USD`
- Display symbols: ¥ / € / $
- SC form: dropdown with symbol, defaults to CNY
- PO/GR: read currency via `LEFT JOIN sc_records` at query time — NO column on PO/GR tables
- Migration SQL: `ALTER TABLE sc_records ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'`

### A2. SC Allow No Vendor

- Verify `sc_records.vendor_id` allows NULL (or make it nullable)
- SC form: vendor field becomes optional
- Add bilingual prompt on SC create/edit form (see E6)
- PO/GR vendor logic: unchanged (vendor still required for PO)

### A3. Vendor ID Auto-Generation

- Auto-generate `vendor_id` on creation: `V` + 6-digit zero-padded sequence from `(SELECT COALESCE(MAX(CAST(SUBSTR(vendor_id, 2) AS INTEGER)), 0) + 1 FROM vendors)`
- Create form: remove Vendor ID input field
- Edit form: Vendor ID shown as read-only
- Migration: existing vendor IDs preserved as-is; sequence picks up after max existing

### A4. Audit → Record Rename

Scope: rename "audit" to "record" across all layers.

| Layer | Old | New |
|---|---|---|
| DB table | `audit_logs` | `operation_records` |
| Python module | `audit_service.py` | `record_service.py` |
| Python functions | `write_audit_log`, `search_audit_logs` | `write_operation_record`, `search_operation_records` |
| JS bridge method | `search_audit_logs` | `search_operation_records` |
| UI labels | "Audit Log" | "Operation Record" |
| i18n keys | `audit.*` | `record.*` |

### A5. Log Time Format

- All timestamps displayed in UI use format: `YYYY-MM-DD HH:MM:SS` (24-hour)
- Apply to operation records, entity timestamps shown in views
- Format on Python side before sending to frontend

---

## Stream B: Import/Export

### B1. Template Export

For SC, PO, GR: "Download Template" button alongside "Import".

- Template contains all importable fields as column headers
- Second row contains hints (required/optional, enum values, format)
- SC template includes `status` column with allowed values
- Format: `.xlsx`

### B2. Import Flow

1. User selects filled `.xlsx` via file picker
2. Frontend reads with `XLSX` library → sends rows array to `callApi('import_scs' / 'import_pos' / 'import_grs', { rows })`
3. Python backend:
   - Validate ALL rows first (required fields, enum values, FK references)
   - If errors: return ALL errors (row + field + message), no partial insert
   - If valid: write all rows in single transaction with direct status values (bypass state machine — users write status directly)
   - Generate operation records for each row
4. Success response: `{ count: N }`; Failure: `{ errors: [{ row, field, message }] }`

### B3. FK Dependencies

- PO import: `sc_id` + `vendor_id` must exist
- GR import: `po_id` must exist
- Import ordering: SC first → Vendor → PO → GR

### B4. Concurrency

- Import acquires a global import lock (`import:lock`) to avoid conflicts during batch write
- Single transaction: all-or-nothing

---

## Stream C: Registration & Identity

### C1. Registration Flow

On login screen, when `get_current_user` returns `PermissionDenied`:

1. Error state now includes a **"Register"** button
2. Registration form overlay:
   - `machine_id` (read-only, pre-filled)
   - `user_name` (required)
   - `email` (required, validated format)
3. On submit → `callApi('register_user', { machine_id, user_name, email })`
4. New API endpoint `register_user`: no auth required; only available when machine_id not yet registered
5. On success: auto-login as requester
6. Created user: `role = 'requester'`, `status = 'active'`

### C2. Duplicate Prevention

- If `machine_id` already exists → reject: "This machine ID is already registered. Contact an administrator."
- Email: soft warning if duplicate, but allow (same person may have multiple machines)

### C3. Detail Views — Show Name

- SC/PO/GR list and detail views: JOIN `users` table and display `user_name` instead of `machine_id` for requester/actor fields
- Operation records: resolve user references to names where possible

---

## Stream D: Email Overhaul

### D1. Subject Line Convention

Format: `[POMP] <action> <entity_type> from <abbreviation> <YYYYMMDD>-<NNN>`

Abbreviation rules:
- "Zhou, Liwei" → "ZLiwei" (first char of surname + given name, no punctuation)
- "Liwei Zhou" → "LZhou" (first char of first token + last token)
- Sequence: per-day 3-digit counter (`001`, `002`, ...)

Examples: `[POMP] submitted SC from ZLiwei 20260625-001`

### D2. Body Format — Simplified HTML Tables

Two sections, simple HTML tables (thin borders, no background colors, standard font):

**Table 1 — Notification Info:**
Entity Type, Entity ID, Event, Operator, Status, Attachments

**Table 2 — Detail Info:**
All entity fields as key-value rows (field name | value), with removals per D3.

### D3. Field Removals & Renames

**Removed from SC emails:** Consumed Amount, Available Amount, Created At, Updated At, Pending Date, Approved Date, Closed Date

**Removed from PO emails:** Consumed Amount, Pending Est. (excl. tax), Pending Est. (incl. tax), Open PO Amount, Activing Date, Created At, Updated At

**Removed from GR emails:** Created At, Pending Date, Approved Date, Cancelled At, Confirmed At

**Renames:**

| Old | New | Entity |
|---|---|---|
| Estimated Amount (Net) | GR Application Amount (Net) | GR |
| Gross Cost (Tax incl.) | GR Application Amount (Gross) | GR |
| Contract Value | GR Value | GR |
| Pending Est. (excl. tax) | Pending GR amount (Net) | PO |
| Pending Est. (incl. tax) | Pending GR amount (Gross) | PO |
| Manager Confirm status | To be confirm | All |

### D4. Non-Auto Emails: Draft → Preview → Manual Send

- **Auto emails** (threshold_date, threshold_amount, custom_schedule): send automatically, unchanged
- **Non-auto emails** (status_change): NO server-side send. Instead:
  1. App generates email content (subject + HTML body)
  2. Preview modal shows: subject, to/cc, rendered body
  3. User clicks "Open in Outlook" → `win32com` creates Outlook draft + opens it
  4. User manually sends from Outlook
- Remove auto-send log display for non-auto emails (no "sent/failed" status shown)

### D5. Reminders — Requester Only

- Threshold and periodic reminder emails: `to_recipients` = requester only
- Admins are NOT included in reminder emails

### D6. Attachment Names

- Add `attachments` field to Notification Info table
- Source: entity's attachment columns or files table
- Display comma-separated filenames

---

## Stream E: UI & Localization

### E1. Default Language → English

- Change default `locale` in `i18n/index.js` from `'zh-CN'` to `'en-US'`
- When no saved preference exists, app starts in English
- Locale switcher toggle: unchanged

### E2. SC/PO List — Date Columns

- SC List table: add `start_date` and `end_date` columns, both `sortable="custom"`
- PO List table: add `start_date` and `end_date` columns, both `sortable="custom"`
- Columns already exist in DB; only frontend table config changes

### E3. Vendor Selection Display

- SC/PO vendor dropdowns and display: show `vendor_name - company_name_cn - vendor_id - ksrm_vendor_code`
- Example: "ABC Corp - ABC贸易有限公司 - V000001 - KSRM12345"
- All four fields shown in selection lists for quick identification

### E4. Vendor Form Labels

- "Vendor Name" → "Vendor Name (Full Name Required)" (English)
- "供应商名称" → "供应商名称（需全称）" (Chinese)
- Remove Vendor ID input from create form (auto-generated, see A3)

### E5. PO Deadline Label

- Chinese: "截止日期" → "合同结束日期"
- English: "Deadline" → "Contract End Date"

### E6. SC Bilingual Vendor Prompt

Info box on SC create/edit form, always shown in BOTH languages regardless of system locale:

> **中文:** 如果需要采购遴选供应商，可在PO生成后再补充供应商信息。如不需要采购审核，需要填写经比价确定或唯一指定的供应商信息（请将比价证明或唯一指定证明材料作为附件上传）

> **English:** If procurement vendor selection is required, vendor information can be supplemented after PO creation. If procurement review is not required, please provide vendor information determined through price comparison or sole-source designation (please upload price comparison proof or sole-source designation documents as attachments)

### E7. Installer Output

- `build.ps1` after producing `POMP_Setup_<version>.exe`:
  - Copy to `release/POMP_Setup.exe` (non-versioned, overwrite)
  - Copy versioned to `release/history/POMP_Setup_<version>.exe`
- Auto-update: app checks fixed path `release/POMP_Setup.exe`

---

## Migration Summary

| # | Migration SQL |
|---|---|
| A1 | `ALTER TABLE sc_records ADD COLUMN currency TEXT NOT NULL DEFAULT 'CNY'` |
| A2 | Ensure `sc_records.vendor_id` is nullable (if not already) |
| A4 | `ALTER TABLE audit_logs RENAME TO operation_records` (requires schema version bump) |

---

## API Changes

| Method | Type | Description |
|---|---|---|
| `register_user` | New | Create user as requester (no auth required) |
| `import_scs` | New | Bulk import SC rows with direct status |
| `import_pos` | New | Bulk import PO rows with direct status |
| `import_grs` | New | Bulk import GR rows with direct status |
| `search_operation_records` | Renamed | Was `search_audit_logs` |
| `generate_email_draft` | New | Generate email content for preview (non-auto only) |
