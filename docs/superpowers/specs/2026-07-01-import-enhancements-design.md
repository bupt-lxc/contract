# Import enhancements — status restrictions, required fields, and preview dialog

## Summary

Restrict SC/PO/GR imports to specific statuses, add required-field validation, show
import rules on templates and dialogs, and add a two-step preview→confirm flow
(patterned on the existing vendor import) so users can review and select rows
before they are written to the database.

## Backend

### `sc_gr_app/services/import_service.py`

**Status restrictions** — replace the permissive status sets:

```
SC_IMPORT_ALLOWED_STATUSES  = {"approved", "finished"}
PO_IMPORT_ALLOWED_STATUSES  = {"active", "finished"}
GR_IMPORT_ALLOWED_STATUSES  = {"approved", "finished"}
```

**Required-field validation** (`_validate_*_rows`):

| Entity | New required fields |
|--------|-------------------|
| SC     | `sc_no` (was optional) |
| PO     | `po_no` (was optional) |
| GR     | `gr_no`, `con_value`, `delivery_from`, `delivery_to` (all were optional) |

Existing required fields (`sc_amount`, `status` for SC; `sc_id`, `po_amount`, `status`
for PO; `po_id`, `estimated_amount`, `status` for GR) remain unchanged.

**New preview functions** — one per entity, following the `vendor_service.preview_import`
pattern. Each function accepts pre-parsed rows (the frontend parses the xlsx file
client-side with the `xlsx` library, same as today) and returns them annotated.

1. Connects to the DB to check foreign-key existence (requester_id, sc_id, po_id, vendor_id)
2. Runs the same validation rules as `_validate_*_rows`
3. Returns every row annotated with `_errors: list[str]`, `_valid: bool`
4. Does NOT insert into the database

```
preview_sc_import(config, rows: list[dict]) → list[dict]
preview_po_import(config, rows: list[dict]) → list[dict]
preview_gr_import(config, rows: list[dict]) → list[dict]
```

The existing `import_scs`/`import_pos`/`import_grs` functions serve as the confirm step
(they already re-validate on write). No structural changes needed to those functions.

### `sc_gr_app/api/bridge.py`

Three new bridge methods:

- `preview_sc_import` — accepts `{ rows }` payload (parsed by frontend), calls `import_service.preview_sc_import`, returns rows annotated with `_errors` / `_valid`
- `preview_po_import` — same for PO
- `preview_gr_import` — same for GR

The existing `import_scs`/`import_pos`/`import_grs` bridge methods remain as the
confirm endpoints and are unchanged.

### Templates (in bridge.py: `download_sc_template`, `download_po_template`, `download_gr_template`)

- Add a merged info row at the top of each template sheet listing:
  - Allowed status values
  - Required fields
- Update status hint values to reflect the restricted status sets
- Update hints for newly-required fields from "Optional" to "Required"

## Frontend

### New component: `src/components/common/ImportPreviewDialog.vue`

A reusable import preview dialog generalized from `VendorImportDialog.vue`.

**Two steps:**

1. **File select** — upload area (el-upload drag) with an info box above showing the
   import rules for the current entity type (allowed statuses, required fields).
   A "Download Template" link beside the upload area.

2. **Preview table** — after file is parsed and preview API returns:
   - Summary bar: file name, counts (valid/invalid/selected)
   - Full-column scrollable table with:
     - **Checkbox column** — default checked for valid rows, disabled for invalid rows
     - All field columns from the imported file
     - **Validation column** — red errors or green checkmark
   - Invalid rows are visually distinguished (grey text or row styling)

**Footer:** Cancel | Re-select file | Confirm Import (N selected)

**Props:** `visible`, `entityType` ("SC" | "PO" | "GR"), and entity-specific config:
- `columns`: array of `{ prop, label, width? }` for the preview table
- `rulesText`: string displayed in the info box
- `apiPrefix`: "sc" | "po" | "gr" for resolving API method names

**Emits:** `update:visible`, `imported`

The file is parsed client-side with `xlsx` (same as today), then sent to the preview
API for server-side validation. This keeps the parsing in JS where it already works.

### Updates to list views

Replace the current `<el-dialog>` import blocks in:

- `src/views/ScListView.vue`
- `src/views/PoListView.vue`
- `src/views/GrListView.vue`

Each replaces its `<el-dialog>` with `<ImportPreviewDialog>` configured for that
entity type. The existing `downloadTemplate` buttons remain in the toolbar.

New flow per list view:
1. Click Import → dialog opens (step 1: file select)
2. Select xlsx file → JS parses rows → calls `preview_*_import` API
3. Dialog shows preview table with checkboxes and validation results
4. User unchecks any row they don't want, clicks "Confirm Import"
5. Checked rows are sent to `import_*` API → success → dialog closes → list refreshes

### i18n

Add import-related i18n keys under each entity's section for:
- Info box text (allowed statuses, required fields)
- Preview labels (valid/invalid rows, selected count)
- Template instruction text

## Testing

### Backend tests (`tests/test_import_service.py` or similar)

- SC import rejects statuses outside `{approved, finished}`
- PO import rejects statuses outside `{active, finished}`
- GR import rejects statuses outside `{approved, finished}`
- SC import fails when `sc_no` is missing
- PO import fails when `po_no` is missing
- GR import fails when `gr_no`, `con_value`, `delivery_from`, or `delivery_to` is missing
- Preview functions return rows annotated with `_errors` and `_valid` without inserting
- Confirm import still writes correctly with the new required fields present

## Files changed

| File | Change |
|------|--------|
| `sc_gr_app/services/import_service.py` | Status constants, validation rules, new preview functions |
| `sc_gr_app/api/bridge.py` | Three new preview endpoints, template info row updates |
| `frontend/src/components/common/ImportPreviewDialog.vue` | **New** — reusable import preview dialog |
| `frontend/src/views/ScListView.vue` | Replace import dialog with ImportPreviewDialog |
| `frontend/src/views/PoListView.vue` | Replace import dialog with ImportPreviewDialog |
| `frontend/src/views/GrListView.vue` | Replace import dialog with ImportPreviewDialog |
| `frontend/src/i18n/locales/en-US.js` | New import-related keys |
| `frontend/src/i18n/locales/zh-CN.js` | New import-related keys |
| `tests/test_import_service.py` | Tests for status restrictions and required fields |
