# Import enhancements — status restrictions, required fields, and preview dialog

## Summary

Restrict SC/PO/GR imports to specific statuses, add required-field validation, show
import rules on templates and dialogs, and add a two-step preview→confirm flow
(patterned on the existing vendor import) so users can review and select rows
before they are written to the database.

---

## Backend

### `sc_gr_app/services/import_service.py`

#### 1. Status restrictions

Replace the existing permissive status constants:

```python
# Before
SC_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "finished"}
PO_ALLOWED_STATUSES  = {"draft", "active", "finished"}
GR_ALLOWED_STATUSES  = {"draft", "manager_confirm", "pending", "approved", "denied", "finished"}

# After
SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}
PO_IMPORT_ALLOWED_STATUSES = {"active", "finished"}
GR_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}
```

The import service functions reference these new constants instead.

#### 2. Required-field validation

Updated `_validate_*_rows` functions — required field lists change as follows.

**SC** (`_validate_sc_rows`):

- was required: `sc_amount`, `status`
- **add to required: `sc_no`**
- new required set: `sc_no`, `sc_amount`, `status`

**PO** (`_validate_po_rows`):

- was required: `sc_id`, `po_amount`, `status`
- **add to required: `po_no`**
- new required set: `sc_id`, `po_no`, `po_amount`, `status`

**GR** (`_validate_gr_rows`):

- was required: `po_id`, `estimated_amount`, `status`
- **add to required: `gr_no`, `con_value`, `delivery_from`, `delivery_to`**
- new required set: `po_id`, `gr_no`, `estimated_amount`, `con_value`, `delivery_from`, `delivery_to`, `status`

The validation function for each entity checks each required field for empty/whitespace-only
values and returns `{"row": i, "field": field, "message": f"{field} is required"}` errors.
Existing foreign-key checks (requester_id exists in users, sc_id exists in sc_records,
po_id exists in pos, vendor_id exists in vendors) remain unchanged.

#### 3. New preview functions

Three new functions that validate rows without inserting. Each follows the
`vendor_service.preview_import` pattern — accepts pre-parsed rows (the frontend
parses the xlsx file client-side with the `xlsx` library) and returns them annotated.

```
preview_sc_import(config: AppConfig, rows: list[dict]) → list[dict]
preview_po_import(config: AppConfig, rows: list[dict]) → list[dict]
preview_gr_import(config: AppConfig, rows: list[dict]) → list[dict]
```

Each preview function:

1. Skips template meta rows (rows where the ID field contains `[EXAMPLE]` or hint text
   with spaces/parens) — same logic as `_is_template_meta_row`
2. Connects to the DB to run foreign-key existence checks:
   - SC: checks `requester_id` exists in `users`
   - PO: checks `sc_id` exists in `sc_records`, `vendor_id` exists in `vendors` (if provided)
   - GR: checks `po_id` exists in `pos`
3. Runs the full `_validate_*_rows` validation on every row (status restrictions,
   required fields, foreign keys)
4. Annotates each row with `_errors: list[str]` (one entry per validation failure)
   and `_valid: bool` (true when `_errors` is empty)
5. Returns all rows — even invalid ones — so the frontend can display them all in the
   preview table; only valid rows will be selectable for import
6. Does NOT insert into the database, does NOT acquire locks

The existing `import_scs`/`import_pos`/`import_grs` functions serve as the confirm step.
They already re-validate on write (running `_validate_*_rows` inside a transaction),
so no structural changes are needed to those functions — only the status constants
and validation rules they reference are updated.

### `sc_gr_app/api/bridge.py`

#### New bridge methods

Three new endpoints, each accepting `{ rows }` from the frontend:

```python
def preview_sc_import(self, payload) -> dict:
    """Validate SC import rows without inserting. Returns annotated rows."""
    user = self._require_current_user()
    payload = self._required_payload(payload)
    rows = _require_payload_field(payload, "rows")
    if not isinstance(rows, list) or len(rows) == 0:
        return fail(ValidationError("rows must be a non-empty list"))
    preview = import_service.preview_sc_import(self.config, rows)
    return ok({"rows": preview})

def preview_po_import(self, payload) -> dict:
    # Same pattern as preview_sc_import

def preview_gr_import(self, payload) -> dict:
    # Same pattern as preview_sc_import
```

The existing `import_scs`/`import_pos`/`import_grs` bridge methods remain as the
confirm endpoints and are unchanged.

#### Template downloads — info row and hint updates

Each `download_*_template` method in bridge.py generates an xlsx file with three rows:

- **Row 1: Headers** — column names
- **Row 2: Hints** — brief field-level instructions
- **Row 3: Sample** — one example row with `[EXAMPLE]` as the ID

**New: Row 0 — merged info row.** A 4th row is added *above* the current header row
(all existing rows shift down by 1) as a merged cell spanning all columns. This row
contains a human-readable instruction block.

**SC template** (`download_sc_template`):

Info row text (zh-CN):
```
导入说明：仅允许导入状态为 "Approved（已审批）" 或 "Finished（已完成）" 的 SC 记录。
必填字段：SC NO（SC编号）、SC Amount（SC金额）、Status（状态）。
SC ID 留空将自动生成。
```

Info row text (en-US):
```
Import Rules: Only SC records with status "approved" or "finished" can be imported.
Required fields: SC NO, SC Amount, Status.
Leave SC ID empty to auto-generate.
```

Hint row updates:
- `sc_id`: "Optional (auto-generated if empty)" — unchanged
- `sc_no`: **"Required"** (was "Optional")
- `requester_id`: "Optional (defaults to importer)" — unchanged
- `status`: **"approved/finished"** (was "draft/pending/approved/finished/denied/manager_confirm")
- `sc_amount`: "Required (e.g. 50000)" — unchanged

**PO template** (`download_po_template`):

Info row text (zh-CN):
```
导入说明：仅允许导入状态为 "Active（进行中）" 或 "Finished（已完成）" 的 PO 记录。
必填字段：SC ID（关联SC编号）、PO NO（PO编号）、PO Amount（PO金额）、Status（状态）。
PO ID 留空将自动生成。
```

Info row text (en-US):
```
Import Rules: Only PO records with status "active" or "finished" can be imported.
Required fields: SC ID, PO NO, PO Amount, Status.
Leave PO ID empty to auto-generate.
```

Hint row updates:
- `po_id`: "Optional (auto-generated if empty)" — unchanged
- `sc_id`: "Required (must exist)" — unchanged
- `po_no`: **"Required"** (was "Optional")
- `status`: **"active/finished"** (was "draft/active/finished")

**GR template** (`download_gr_template`):

Info row text (zh-CN):
```
导入说明：仅允许导入状态为 "Approved（已审批）" 或 "Finished（已完成）" 的 GR 记录。
必填字段：PO ID（关联PO编号）、GR NO（GR编号）、Estimated Amount（预估金额）、
         Con Value（合同金额）、Delivery From（交付开始日期）、
         Delivery To（交付结束日期）、Status（状态）。
GR ID 留空将自动生成。
```

Info row text (en-US):
```
Import Rules: Only GR records with status "approved" or "finished" can be imported.
Required fields: PO ID, GR NO, Estimated Amount, Con Value, Delivery From,
                 Delivery To, Status.
Leave GR ID empty to auto-generate.
```

Hint row updates:
- `gr_id`: "Optional (auto-generated if empty)" — unchanged
- `po_id`: "Required (must exist)" — unchanged
- `gr_no`: **"Required"** (was "Optional")
- `estimated_amount`: "Required" — unchanged
- `con_value`: **"Required"** (was "Optional")
- `delivery_from`: **"Required (YYYY-MM-DD)"** (was "YYYY-MM-DD")
- `delivery_to`: **"Required (YYYY-MM-DD)"** (was "YYYY-MM-DD")
- `status`: **"approved/finished"** (was "draft/manager_confirm/pending/approved/denied/finished")

**Implementation note for the info row:** The current template generation builds raw
xlsx XML manually. To add a merged info row, we need to:

1. Shift all existing row indices from `r="1"/r="2"/r="3"` to `r="2"/r="3"/r="4"`
2. Add a new row `r="1"` containing a single merged cell spanning columns A through
   the last header column, with the info text as inline string content
3. Add a `<mergeCells>` element in the sheet XML: `<mergeCell ref="A1:O1"/>`
   (where O varies by entity — SC=12 cols, PO=15 cols, GR=15 cols)

---

## Frontend

### New component: `src/components/common/ImportPreviewDialog.vue`

A reusable import preview dialog generalized from `VendorImportDialog.vue`.

#### Props

| Prop | Type | Description |
|------|------|-------------|
| `visible` | Boolean | Dialog visibility |
| `entityType` | String | `"SC"`, `"PO"`, or `"GR"` — drives API method names and labels |
| `columns` | Array | Preview table columns: `[{ prop: string, label: string, width?: string }]` |
| `rulesText` | String | i18n text shown in the info box on step 1, describing allowed statuses and required fields |

#### Step 1: File select

Template structure:
```
┌─────────────────────────────────────────────────┐
│  Import [Entity Type]                     [×]   │
├─────────────────────────────────────────────────┤
│                                                 │
│  ┌─ Info Box ──────────────────────────────┐   │
│  │  ℹ️ Import Rules:                         │   │
│  │  Only [entity] records with status       │   │
│  │  [allowed] can be imported.              │   │
│  │  Required fields: [list].                │   │
│  │  Leave [ID] empty to auto-generate.      │   │
│  └──────────────────────────────────────────┘   │
│                                                 │
│  Download Template                               │
│                                                 │
│       ┌─────────────────────────┐               │
│       │      📁 Drop file       │               │
│       │   or click to upload    │               │
│       └─────────────────────────┘               │
│       Only .xlsx/.xls files                      │
│                                                 │
├─────────────────────────────────────────────────┤
│                                    [ Cancel ]    │
└─────────────────────────────────────────────────┘
```

- The info box is a styled `el-alert` (type="info") containing `rulesText`
- "Download Template" is a text link/button that calls `download_*_template` API
  (triggers a file save dialog via the existing `save_file` bridge method)
- The upload area is an `el-upload` with `drag`, `accept=".xlsx,.xls"`, `:auto-upload="false"`,
  `:limit="1"`, `:on-change="handleFileSelect"`

#### Step 2: Preview table

After the user selects a file, the dialog transitions to step 2:

```
┌─────────────────────────────────────────────────┐
│  Import [Entity Type]                     [×]   │
├─────────────────────────────────────────────────┤
│  File: SC_Import.xlsx                            │
│  [✓ Valid: 5]  [✗ Invalid: 2]  [☐ Selected: 5]  │
│                                                 │
│  ┌─ Preview Table (scrollable) ─────────────┐   │
│  │ ☑ │ # │ SC ID │ SC NO │ ... │ Validation │   │
│  │───┼───┼───────┼───────┼─────┼────────────│   │
│  │ ☑ │ 1 │ SC-X  │ SC-01 │ ... │ ✓ Valid    │   │
│  │ ☑ │ 2 │       │ SC-02 │ ... │ ✓ Valid    │   │
│  │ ☐ │ 3 │ SC-Y  │       │ ... │ ✗ sc_no is │   │
│  │   │   │       │       │     │   required  │   │
│  │ ☑ │ 4 │ SC-Z  │ SC-03 │ ... │ ✓ Valid    │   │
│  │ ☐ │ 5 │       │ SC-04 │ ... │ ✗ Invalid  │   │
│  │   │   │       │       │     │   status:   │   │
│  │   │   │       │       │     │   draft     │   │
│  └───────────────────────────────────────────┘   │
│                                                 │
├─────────────────────────────────────────────────┤
│        [ Cancel ]  [ Re-select ]  [ Import (3) ] │
└─────────────────────────────────────────────────┘
```

**Table behavior:**

- **Checkbox column (`type="selection"`)**: Defaults to checked for rows where `_valid === true`,
  disabled/unchecked for rows where `_valid === false`. The user can manually uncheck
  valid rows they don't want to import.
- **Row number column (`type="index"`)**: Sequential row number starting from 1 (excluding
  the template header/hint/sample rows that are skipped during parsing).
- **Data columns**: One column per field in `columns` prop, with width configurable.
  For invalid rows, the cell text is rendered in a lighter/grey color to visually
  distinguish them.
- **Validation column**: The last column. For valid rows: green checkmark icon + "Valid"
  text. For invalid rows: red X icon(s) + error message(s) per validation failure,
  one per line.
- **Summary bar**: Above the table, shows:
  - File name (extracted from the selected file path)
  - Count tags using `el-tag`: valid count (green), invalid count (red), selected count (blue)
  - Selected count updates in real-time as the user checks/unchecks rows

**Data flow for step 2:**

1. `handleFileSelect(file)` is called when the user picks a file
2. The file's raw bytes are read via `file.raw.arrayBuffer()`
3. `XLSX.read(data, { type: 'array' })` parses the workbook
4. `XLSX.utils.sheet_to_json(ws, { defval: '' })` converts to rows
5. Rows are sent to `preview_*_import` API → backend validates and returns annotated rows
6. Annotated rows are stored in `previewRows` ref, displayed in the table
7. A `computed` property `selectedRows` tracks which valid rows are currently checked

**Footer buttons:**

- **Cancel** — always visible, closes the dialog and resets state
- **Re-select** — visible in step 2 before import completes, resets to step 1
- **Import (N)** — visible in step 2 when at least one valid row is checked;
  N is the count of currently checked rows; calls `confirmImport()`

**Confirm import flow:**

```javascript
async function confirmImport() {
  importing.value = true
  try {
    // Strip _errors, _valid annotations before sending
    const cleanRows = selectedRows.value.map(r => {
      const { _errors, _valid, ...rest } = r
      return rest
    })
    const apiMethod = `import_${props.entityType.toLowerCase()}s` // e.g. "import_scs"
    const result = await callApi(apiMethod, { rows: cleanRows })
    // Show result alert
    if (result.ok) {
      importResult.value = result
    } else {
      importResult.value = result
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    importing.value = false
  }
}
```

**After import completes**, the result is displayed as an `el-alert` below the table:
- Success: shows "Imported N records, skipped M duplicates"
- Partial failure: shows the error list from the backend

A "Done" button replaces the footer to close the dialog and emit `imported`.

#### Emits

| Event | When | Payload |
|-------|------|---------|
| `update:visible` | Dialog close requested | `false` |
| `imported` | Import completed successfully | none (parent refreshes list) |

### Updates to list views

Each list view replaces its current `<el-dialog>` import block with
`<ImportPreviewDialog>`. The existing template download toolbar buttons remain unchanged.

#### ScListView.vue

```vue
<!-- Before: <el-dialog v-model="importVisible" title="Import SC" width="500px"> ... -->
<ImportPreviewDialog
  v-model:visible="importVisible"
  entity-type="SC"
  :columns="scImportColumns"
  :rules-text="$t('sc.importRules')"
  @imported="searchScs"
/>
```

`scImportColumns`:
```javascript
const scImportColumns = [
  { prop: 'sc_id', label: 'SC ID', width: '160' },
  { prop: 'sc_no', label: t('sc.scNo'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'request_type', label: t('sc.requestType'), width: '100' },
  { prop: 'cost_center', label: t('sc.costCenter'), width: '100' },
  { prop: 'sc_amount', label: t('sc.amount'), width: '100' },
  { prop: 'service_period_start', label: t('sc.periodStart'), width: '110' },
  { prop: 'service_period_end', label: t('sc.periodEnd'), width: '110' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'description', label: t('common.description'), width: '140' },
  { prop: 'currency', label: t('sc.currency'), width: '70' },
  { prop: 'internal_system_number', label: t('sc.internalSystemNumber'), width: '100' },
]
```

#### PoListView.vue

Same pattern, `entity-type="PO"`, PO-specific columns and rules text.

#### GrListView.vue

Same pattern, `entity-type="GR"`, GR-specific columns and rules text.

### i18n additions

New keys needed in `en-US.js` and `zh-CN.js`:

```javascript
// en-US
sc: {
  importRules: "Only SC records with status \"Approved\" or \"Finished\" can be imported. Required fields: SC NO, SC Amount, Status. Leave SC ID empty to auto-generate."
  // ...existing keys
}
po: {
  importRules: "Only PO records with status \"Active\" or \"Finished\" can be imported. Required fields: SC ID, PO NO, PO Amount, Status. Leave PO ID empty to auto-generate."
  // ...existing keys
}
gr: {
  importRules: "Only GR records with status \"Approved\" or \"Finished\" can be imported. Required fields: PO ID, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. Leave GR ID empty to auto-generate."
  // ...existing keys
}
common: {
  importValid: "Valid: {n}",
  importInvalid: "Invalid: {n}",
  importSelected: "Selected: {n}",
  importReSelect: "Re-select",
  importConfirm: "Import ({n})",
  importFile: "File",
  importSelectFile: "Select file",
  importDropHint: "Drop file here or click to upload",
  importFormatHint: "Only .xlsx/.xls files",
}
```

```javascript
// zh-CN
sc: {
  importRules: "仅允许导入状态为"Approved（已审批）"或"Finished（已完成）"的SC记录。必填字段：SC NO（SC编号）、SC Amount（SC金额）、Status（状态）。SC ID留空将自动生成。"
}
po: {
  importRules: "仅允许导入状态为"Active（进行中）"或"Finished（已完成）"的PO记录。必填字段：SC ID（关联SC编号）、PO NO（PO编号）、PO Amount（PO金额）、Status（状态）。PO ID留空将自动生成。"
}
gr: {
  importRules: "仅允许导入状态为"Approved（已审批）"或"Finished（已完成）"的GR记录。必填字段：PO ID（关联PO编号）、GR NO（GR编号）、Estimated Amount（预估金额）、Con Value（合同金额）、Delivery From（交付开始日期）、Delivery To（交付结束日期）、Status（状态）。GR ID留空将自动生成。"
}
common: {
  importValid: "有效: {n}",
  importInvalid: "无效: {n}",
  importSelected: "已选: {n}",
  importReSelect: "重新选择",
  importConfirm: "确认导入 ({n})",
  importFile: "文件",
  importSelectFile: "选择文件",
  importDropHint: "将文件拖到此处或点击上传",
  importFormatHint: "仅支持 .xlsx/.xls 文件",
}
```

---

## Testing

### Backend tests (`tests/test_import_service.py`)

Test data setup: create test users via direct INSERT, prepare row dicts with
varying validity, call preview functions and import functions, assert outcomes.

**Status restriction tests:**

1. `test_sc_import_rejects_draft_status` — row with status `"draft"` → `_valid: false`, error mentions "Invalid status"
2. `test_sc_import_accepts_approved_status` — row with status `"approved"` → `_valid: true`
3. `test_sc_import_accepts_finished_status` — row with status `"finished"` → `_valid: true`
4. `test_po_import_rejects_draft_status` — row with status `"draft"` → rejected
5. `test_po_import_accepts_active` / `accepts_finished` — `"active"` and `"finished"` accepted
6. `test_gr_import_rejects_draft_status` — row with status `"draft"` → rejected
7. `test_gr_import_rejects_pending_status` — row with status `"pending"` → rejected
8. `test_gr_import_accepts_approved` / `accepts_finished` — `"approved"` and `"finished"` accepted

**Required-field tests:**

9. `test_sc_import_fails_without_sc_no` — empty `sc_no` → `_valid: false`, error mentions "sc_no is required"
10. `test_po_import_fails_without_po_no` — empty `po_no` → `_valid: false`
11. `test_gr_import_fails_without_gr_no` — empty `gr_no` → `_valid: false`
12. `test_gr_import_fails_without_con_value` — empty `con_value` → `_valid: false`
13. `test_gr_import_fails_without_delivery_from` — empty `delivery_from` → `_valid: false`
14. `test_gr_import_fails_without_delivery_to` — empty `delivery_to` → `_valid: false`

**Preview function tests:**

15. `test_preview_sc_import_annotates_rows` — preview returns rows with `_errors` and `_valid` keys, no rows inserted into DB
16. `test_preview_po_import_annotates_rows` — same for PO
17. `test_preview_gr_import_annotates_rows` — same for GR
18. `test_preview_skips_template_meta_rows` — rows with `[EXAMPLE]` ID or hint text are excluded from preview results

**Confirm import tests:**

19. `test_confirm_sc_import_with_required_fields` — full import succeeds with `sc_no`, `sc_amount`, `status` = approved
20. `test_confirm_po_import_with_required_fields` — full import succeeds with all required fields
21. `test_confirm_gr_import_with_required_fields` — full import succeeds with all required fields including `gr_no`, `con_value`, `delivery_from`, `delivery_to`

---

## Files changed

| File | Change |
|------|--------|
| `sc_gr_app/services/import_service.py` | Status constants, validation rules, new preview functions |
| `sc_gr_app/api/bridge.py` | Three new preview endpoints, template xlsx generation with info row + updated hints |
| `frontend/src/components/common/ImportPreviewDialog.vue` | **New** — reusable two-step import preview dialog |
| `frontend/src/views/ScListView.vue` | Replace inline `<el-dialog>` import block with `<ImportPreviewDialog>` |
| `frontend/src/views/PoListView.vue` | Same |
| `frontend/src/views/GrListView.vue` | Same |
| `frontend/src/i18n/locales/en-US.js` | New import-related i18n keys |
| `frontend/src/i18n/locales/zh-CN.js` | New import-related i18n keys |
| `tests/test_import_service.py` | Tests for status restrictions, required fields, and preview functions |
