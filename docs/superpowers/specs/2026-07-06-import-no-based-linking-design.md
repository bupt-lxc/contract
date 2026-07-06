# Import improvements — NO-based linking, missing fields, date parsing, vendor display

## Summary

Six improvements to the import system:

1. Replace ID-based linking with NO-based linking (SC NO, PO NO, GR NO) for imports
2. Smart date parsing supporting multiple formats (MM/DD/YYYY, etc.)
3. Template example row shows current user's ID for `requester_id`
4. Add missing fields: SC (`vendor_id` comma-separated, `asset`, `asset_nums`), PO (`active_date`)
5. Vendor list shows `vendor_id` as first column
6. Install `openpyxl` dependency

---

## 1. NO-based linking (core change)

### Problem

Current import requires writing `sc_id`/`po_id`/`gr_id` to link records, but these are
system-generated IDs (e.g. `SC-MACHINE-20260706-001`). Users working with legacy data
know their business NOs (SC NO, PO NO, GR NO), not system IDs.

### Design

**SC import:**
- Required: `sc_no`, `sc_amount`, `status`
- `sc_id` hidden from template, auto-generated on insert
- Uniqueness check: any `sc_no` appearing more than once in DB → reject import with error
- Within a single file, duplicate `sc_no` rows → marked `_valid: false` in preview

**PO import:**
- Required: `sc_no` (links to parent SC), `po_no`, `po_amount`, `status`
- `po_id` and `sc_id` hidden from template
- Resolve `sc_no` → `sc_id` via `SELECT sc_id FROM sc_records WHERE sc_no = ?`
- If `sc_no` matches 0 rows → error; matches >1 row → reject with duplicate error
- `po_no` uniqueness check (same logic as SC)

**GR import:**
- Required: `po_no` (links to parent PO), `gr_no`, `estimated_amount`, `con_value`, `delivery_from`, `delivery_to`, `status`
- `gr_id` and `po_id` hidden from template
- Resolve `po_no` → `po_id` via `SELECT po_id FROM pos WHERE po_no = ?`
- `gr_no` uniqueness check (same logic as SC)

**`_is_template_meta_row` update:**
- Checks `sc_no`/`po_no`/`gr_no` for `[EXAMPLE]` marker instead of ID fields

### Validation functions

`_validate_sc_rows`: adds DB-level `sc_no` uniqueness check (reject if duplicate NO in DB).

`_validate_po_rows`: replaces `sc_id` FK check with `sc_no` → `sc_id` resolution. Adds `po_no` uniqueness check.

`_validate_gr_rows`: replaces `po_id` FK check with `po_no` → `po_id` resolution. Adds `gr_no` uniqueness check.

Preview functions (`preview_sc_import`, `preview_po_import`, `preview_gr_import`) mirror validation.

### Import execution

`import_scs`: resolves `sc_no`, auto-generates `sc_id`, inserts into `sc_records` + `sc_vendors` (if `vendor_id` provided).

`import_pos`: resolves `sc_no` → `sc_id`, `po_no`, auto-generates `po_id`, inserts into `pos`.

`import_grs`: resolves `po_no` → `po_id`, `gr_no`, auto-generates `gr_id`, inserts into `gr_requests`.

---

## 2. Smart date parsing

New utility function `parse_date(value: str) → str | None` in `import_service.py`.

Supported formats (tried in order):
```
%Y-%m-%d    2026-01-15
%Y/%m/%d    2026/01/15
%m/%d/%Y    01/15/2026
%m-%d-%Y    01-15-2026
%d/%m/%Y    15/01/2026
%d-%m-%Y    15-01-2026
%Y%m%d      20260115
```

Returns `"YYYY-MM-DD"` on success, `None` on failure (caller adds validation error).

Applied to all date fields during import: `service_period_start`, `service_period_end`, `contract_from`, `contract_to`, `delivery_from`, `delivery_to`, `last_delivery`, `active_date`.

---

## 3. Template example row — requester_id

Each `download_*_template` method now includes `self._require_current_user()` to get the
current user, and writes `user["user_id"]` into the example row's `requester_id` cell
instead of an empty string.

Already done for SC template, needs to be applied to PO and GR templates as well.

---

## 4. Missing fields

### SC import — new fields

| Field | Target | Logic |
|-------|--------|-------|
| `vendor_id` | `sc_vendors` junction table | Comma-separated (e.g. `V000001,V000002`). Each ID validated against `vendors` table. Inserted as separate rows in `sc_vendors`. |
| `asset` | `sc_records.asset` | Y/N, defaults to `'N'` |
| `asset_nums` | `sc_records.asset_nums` | Optional text |

### PO import — new field

| Field | Target | Logic |
|-------|--------|-------|
| `active_date` | `pos.active_date` | Smart date parsing, same as other date fields |

---

## 5. Vendor list — vendor_id column

`VendorListView.vue`: add `<el-table-column prop="vendor_id" label="Vendor ID" width="120" />`
as the first column, before `vendor_name`.

---

## 6. openpyxl dependency

Install `openpyxl` as a project dependency (used by `vendor_service._parse_excel`).
Add to `requirements.txt` or equivalent.

---

## Template headers — summary

### SC template (after, 15 columns)
```
sc_no, vendor_id, requester_id, request_type, cost_center, sc_amount,
service_period_start, service_period_end, status, description, currency,
internal_system_number, calloff_po_id, asset, asset_nums
```

### PO template (after, 15 columns)
```
sc_no, vendor_id, po_no, requester_id, po_amount, status,
contract_from, contract_to, contract_no, payment_frequency,
contract_pos, contract_type, cost_center, purchaser, active_date
```

### GR template (after, 14 columns)
```
po_no, gr_no, requester_id, estimated_amount, con_value, status, remark,
tax_rate, gross_cost, goods_service_description, confirmation_name,
delivery_from, delivery_to, last_delivery
```

---

## Files changed

| File | Change |
|------|--------|
| `sc_gr_app/services/import_service.py` | NO linking, `parse_date` utility, vendor_id comma-split, asset/asset_nums/active_date fields, updated `_is_template_meta_row` |
| `sc_gr_app/api/bridge.py` | Template headers/hints/samples updated; `download_*_template` passes current user ID to example row |
| `frontend/src/views/ScListView.vue` | `scImportColumns` updated to match new template |
| `frontend/src/views/PoListView.vue` | `poImportColumns` updated to match new template |
| `frontend/src/views/GrListView.vue` | `grImportColumns` updated to match new template |
| `frontend/src/views/VendorListView.vue` | Add `vendor_id` as first table column |
| `tests/test_import_service.py` | Tests for NO linking, date parsing, vendor_id comma-split, missing fields |
| `requirements.txt` (or equivalent) | Add `openpyxl` |
