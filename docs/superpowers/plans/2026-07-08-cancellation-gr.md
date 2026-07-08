# Cancellation GR Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Cancellation GR support — a GR subtype with negative amounts for vendor refunds, distinguished by `is_cancellation` field.

**Architecture:** Add `is_cancellation` TEXT column to `gr_requests`, modify CHECK constraints to allow negative amounts when `is_cancellation='Y'`, skip budget checks for Cancellation GRs, update email subjects with "(Cancellation)" prefix, and adapt frontend form/list/export to handle the new field and dynamic amount constraints.

**Tech Stack:** Python 3.x + SQLite3 (backend), Vue 3 + Element Plus (frontend)

---

### Task 1: Database migration v37

**Files:**
- Modify: `sc_gr_app/db/migrations.py` (add `migrate_v37`)

- [ ] **Step 1: Add `migrate_v37` function at end of migrations.py**

Read `sc_gr_app/db/migrations.py` to find the last migration function and its registration in the `_MIGRATIONS` list (at the bottom of the file).

- [ ] **Step 2: Write the migration function**

```python
def migrate_v37(conn):
    """v37: Add is_cancellation column + update amount CHECK constraints for Cancellation GR.

    Cancellation GRs (is_cancellation='Y') allow negative estimated_amount (< 0)
    and non-positive con_value (<= 0). Normal GRs keep the existing constraints.
    """
    has_gr = _table_exists(conn, "gr_requests")
    if not has_gr:
        return

    existing = {row["name"] for row in conn.execute("PRAGMA table_info(gr_requests)")}
    has_is_cancellation = "is_cancellation" in existing

    if not has_is_cancellation:
        # Step A: Add column with default, no table rebuild needed yet
        conn.execute(
            "ALTER TABLE gr_requests ADD COLUMN is_cancellation TEXT NOT NULL DEFAULT 'N'"
            " CHECK (is_cancellation IN ('N', 'Y'))"
        )

    # Step B: Rebuild table with updated amount CHECK constraints
    conn.execute("ALTER TABLE gr_requests RENAME TO gr_requests_old")

    conn.execute("""
        CREATE TABLE gr_requests (
          gr_id TEXT PRIMARY KEY,
          gr_no TEXT,
          po_id TEXT NOT NULL REFERENCES pos(po_id),
          requester_id TEXT NOT NULL REFERENCES users(user_id),
          estimated_amount REAL NOT NULL CHECK (
            (is_cancellation = 'N' AND estimated_amount > 0) OR
            (is_cancellation = 'Y' AND estimated_amount < 0)
          ),
          con_value REAL CHECK (
            con_value IS NULL OR
            (is_cancellation = 'N' AND con_value >= 0) OR
            (is_cancellation = 'Y' AND con_value <= 0)
          ),
          gross_cost REAL,
          tax_rate REAL,
          status TEXT NOT NULL CHECK (status IN ('draft','manager_confirm','pending','approved','denied','finished')),
          remark TEXT,
          created_by TEXT NOT NULL REFERENCES users(user_id),
          created_at TEXT NOT NULL,
          approved_by TEXT REFERENCES users(user_id),
          approved_at TEXT,
          denied_by TEXT REFERENCES users(user_id),
          denied_at TEXT,
          finished_by TEXT REFERENCES users(user_id),
          finished_at TEXT,
          confirmed_at TEXT,
          pending_date TEXT,
          approved_date TEXT,
          submitted_date TEXT,
          goods_service_description TEXT,
          confirmation_name TEXT,
          delivery_from TEXT,
          delivery_to TEXT,
          last_delivery TEXT,
          updated_at TEXT,
          is_cancellation TEXT NOT NULL DEFAULT 'N' CHECK (is_cancellation IN ('N', 'Y'))
        )
    """)

    conn.execute("""
        INSERT INTO gr_requests (
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          gross_cost, tax_rate, status, remark, created_by, created_at,
          approved_by, approved_at, denied_by, denied_at, finished_by,
          finished_at, confirmed_at, pending_date, approved_date,
          submitted_date, goods_service_description, confirmation_name,
          delivery_from, delivery_to, last_delivery, updated_at,
          is_cancellation
        )
        SELECT
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          gross_cost, tax_rate, status, remark, created_by, created_at,
          approved_by, approved_at, denied_by, denied_at, finished_by,
          finished_at, confirmed_at, pending_date, approved_date,
          submitted_date, goods_service_description, confirmation_name,
          delivery_from, delivery_to, last_delivery, updated_at,
          'N' as is_cancellation
        FROM gr_requests_old
    """)

    conn.execute("DROP TABLE gr_requests_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_gr_requester ON gr_requests(requester_id)")
```

- [ ] **Step 3: Register migration in `_MIGRATIONS` list**

At the bottom of `migrations.py`, find the `_MIGRATIONS` list and append `migrate_v37`:

```python
_MIGRATIONS = [
    # ... existing entries ...
    migrate_v36,
    migrate_v37,
]
```

- [ ] **Step 4: Update schema.sql to match**

In `sc_gr_app/db/schema.sql`, update the `gr_requests` CREATE TABLE statement to match the v37 definition above (add `is_cancellation` column, update CHECK constraints).

- [ ] **Step 5: Run migration to verify**

```bash
cd sc_gr_app && uv run python -c "
from sc_gr_app.db.migrations import migrate
from sc_gr_app.config import default_config
migrate(default_config(is_beta=False))
print('Migration v37 applied successfully')
"
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/db/migrations.py sc_gr_app/db/schema.sql
git commit -m "feat: add v37 migration for is_cancellation column and compound amount CHECK"
```

---

### Task 2: gr_service.py — validation, budget skip, INSERT

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add new validation functions after `_non_negative_number` (after line ~65)**

```python
def _negative_number(value, field: str) -> Decimal:
    """Validate that a numeric value is strictly negative (for Cancellation GR)."""
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValidationError(f"{field} must be negative") from None
    if not number.is_finite() or number >= 0:
        raise ValidationError(f"{field} must be negative")
    return number


def _non_positive_number(value, field: str) -> Decimal:
    """Validate that a numeric value is non-positive (<= 0, for Cancellation GR con_value)."""
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValidationError(f"{field} must be non-positive") from None
    if not number.is_finite() or number > 0:
        raise ValidationError(f"{field} must be non-positive")
    return number
```

- [ ] **Step 2: Update `_validate_gr_creation_context` — add `is_cancellation` parameter, skip budget check**

Change signature (line ~187) from:
```python
def _validate_gr_creation_context(
    config: AppConfig,
    po_sc,
    amount: Decimal,
    gr_status: str = "pending",
) -> None:
```

To:
```python
def _validate_gr_creation_context(
    config: AppConfig,
    po_sc,
    amount: Decimal,
    gr_status: str = "pending",
    is_cancellation: str = "N",
) -> None:
```

And in the active PO + approved SC branch (around line 207-216), wrap the budget check in a condition:

```python
    if po_status == "active" and sc_status == "approved":
        if gr_status not in ("draft", "pending", "manager_confirm"):
            raise ConflictError("Active PO only allows draft, pending or manager_confirm GR")
        # Cancellation GRs skip budget checks (negative amounts don't consume budget)
        if is_cancellation != "Y":
            sc_budget = compute_sc_budget_decimal(config, po_sc["sc_id"])
            po_budget = compute_po_budget_decimal(config, po_sc["po_id"])
            if sc_budget["sc_available_amount"] < amount:
                raise ConflictError("SC available amount is insufficient")
            if po_budget["open_po_amount"] < amount:
                raise ConflictError("PO open amount is insufficient")
        return
```

- [ ] **Step 3: Update `create_gr` — conditionally validate amount, pass is_cancellation, add to INSERT**

At line ~224, replace the `_positive_number` call with conditional:
```python
    is_cancellation = data.get("is_cancellation", "N")
    if is_cancellation == "Y":
        estimated_amount = _negative_number(data["estimated_amount"], "estimated_amount")
    else:
        estimated_amount = _positive_number(data["estimated_amount"], "estimated_amount")
```

At line ~283, update the call to pass `is_cancellation`:
```python
    _validate_gr_creation_context(config, po_sc, estimated_amount, gr_status, is_cancellation)
```

In the INSERT statement (lines ~294-319), add `is_cancellation` to the column list and `is_cancellation` to the VALUES:
```python
    conn.execute(
        """
        insert into gr_requests (
          gr_id, gr_no, po_id, requester_id,
          estimated_amount, con_value, gross_cost, tax_rate,
          status, remark, created_by, created_at, updated_at,
          approved_by, approved_at, denied_by, denied_at,
          submitted_date, pending_date, approved_date,
          goods_service_description, confirmation_name,
          delivery_from, delivery_to, last_delivery,
          is_cancellation
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gr_id,
            data.get("gr_no"),
            po_id,
            requester_id,
            float(estimated_amount),
            None,
            float(gross_cost) if gross_cost is not None else None,
            data.get("tax_rate"),
            gr_status,
            data.get("remark"),
            current_user["user_id"],
            timestamp,
            timestamp,
            None, None, None, None,
            None if is_draft else timestamp,
            None if (is_draft or is_manager_confirm) else timestamp,
            None,
            data.get("goods_service_description"),
            data.get("confirmation_name"),
            data.get("delivery_from"),
            data.get("delivery_to"),
            data.get("last_delivery"),
            is_cancellation,
        ),
    )
```

- [ ] **Step 4: Add comment to `submit_gr` budget check (around line ~459)**

Add a comment above the budget check noting Cancellation GRs naturally skip it:
```python
                # Cancellation GR: estimated_amount < 0, so budget check
                # (positive < negative) is always False — naturally skipped.
                estimated_amount = Decimal(str(before["estimated_amount"]))
```

- [ ] **Step 5: Update `update_gr` draft/pending branch — conditional validation, budget skip, allowed keys**

At line ~682, add `"is_cancellation"` to the allowed keys tuple:
```python
                    allowed = {
                        key: updates[key]
                        for key in (
                            "po_id",
                            "requester_id",
                            "estimated_amount",
                            "tax_rate",
                            "remark",
                            "gr_no",
                            "pending_date",
                            "approved_date",
                            "goods_service_description",
                            "confirmation_name",
                            "delivery_from",
                            "delivery_to",
                            "last_delivery",
                            "is_cancellation",
                        )
                        if key in updates
                    }
```

At line ~707-710, replace the `_positive_number` call with conditional:
```python
                    is_canc = merged.get("is_cancellation", "N")
                    if is_canc == "Y":
                        amount = _negative_number(merged["estimated_amount"], "estimated_amount")
                    else:
                        amount = _positive_number(merged["estimated_amount"], "estimated_amount")
```

At line ~734-752, wrap the budget check in `if is_canc != "Y":`:
```python
                    if not is_draft_gr and is_canc != "Y":
                        old_amount = Decimal(str(before["estimated_amount"]))
                        # ... rest of budget check unchanged ...
```

- [ ] **Step 6: Update `update_gr` approved branch — conditional con_value, budget skip**

At line ~821-823, replace the `_non_negative_number` call with conditional:
```python
                    is_canc = before.get("is_cancellation", "N")
                    if is_canc == "Y":
                        con_value = _non_positive_number(merged["con_value"], "con_value")
                    else:
                        con_value = _non_negative_number(merged["con_value"], "con_value")
```

At line ~825-852, wrap the extra_amount budget check in `if is_canc != "Y":`:
```python
                    extra_amount = con_value - Decimal(str(before["con_value"]))
                    if is_canc != "Y" and extra_amount > 0:
                        sc_budget = compute_sc_budget_decimal(config, sc_id)
                        # ... rest of budget check unchanged ...
```

- [ ] **Step 7: Update `approve_gr` — conditional con_value, budget skip**

At line ~579, replace the `_non_negative_number` call with conditional:
```python
                is_canc = before.get("is_cancellation", "N")
                if con_value is not None:
                    if is_canc == "Y":
                        con_value_amount = _non_positive_number(con_value, "con_value")
                    else:
                        con_value_amount = _non_negative_number(con_value, "con_value")
```

At line ~590-598, wrap the budget check:
```python
                extra_amount = con_value_amount - Decimal(str(before["estimated_amount"]))
                if is_canc != "Y" and extra_amount > 0:
                    sc_budget = compute_sc_budget_decimal(config, sc_id)
                    # ... rest of budget check unchanged ...
```

- [ ] **Step 8: Commit**

```bash
git add sc_gr_app/services/gr_service.py
git commit -m "feat: add is_cancellation support to GR create/update/approve/submit"
```

---

### Task 3: import_service.py — column aliases, validation, INSERT

**Files:**
- Modify: `sc_gr_app/services/import_service.py`

- [ ] **Step 1: Add `is_cancellation` to `_GR_COLUMN_ALIASES` (before the closing `}` at line ~66)**

```python
    "is_cancellation":          ["Is Cancellation", "is_cancellation", "是否取消类型"],
```

- [ ] **Step 2: Add cross-validation in `_validate_gr_rows` (after the status validation block)**

Find `_validate_gr_rows` (line ~537). After the existing field validations, add:

```python
        # --- is_cancellation cross-validation ---
        is_canc = row.get("is_cancellation", "").strip().upper()
        if is_canc not in ("", "Y", "N"):
            errors.append(f"Row {idx+1}: is_cancellation must be 'Y' or 'N', got: {row.get('is_cancellation')}")
        else:
            is_canc = is_canc or "N"  # default to N
            est_raw = row.get("estimated_amount")
            if est_raw is not None:
                try:
                    est_val = float(est_raw)
                    if is_canc == "Y" and est_val >= 0:
                        errors.append(f"Row {idx+1}: Cancellation GR estimated_amount must be negative, got {est_val}")
                    if is_canc == "N" and est_val <= 0:
                        errors.append(f"Row {idx+1}: estimated_amount must be positive, got {est_val}")
                except (ValueError, TypeError):
                    pass

            con_raw = row.get("con_value")
            if con_raw is not None:
                try:
                    con_val = float(con_raw)
                    if is_canc == "Y" and con_val > 0:
                        errors.append(f"Row {idx+1}: Cancellation GR con_value must be <= 0, got {con_val}")
                    if is_canc == "N" and con_val < 0:
                        errors.append(f"Row {idx+1}: con_value must be >= 0, got {con_val}")
                except (ValueError, TypeError):
                    pass

            row["is_cancellation"] = is_canc
```

- [ ] **Step 3: Add same cross-validation in `preview_gr_import`**

Find `preview_gr_import` (line ~737). This function also has inline field validation. Add the same `is_cancellation` cross-validation block from Step 2 before or after the existing field validation loop.

- [ ] **Step 4: Add `is_cancellation` to INSERT in `import_grs`**

Find the INSERT statement in `import_grs` (around line ~823). Add `is_cancellation` to the column list and `row.get("is_cancellation", "N")` to the VALUES tuple.

> **Note:** `import_grs` is the only GR import function (there is no `import_grs_without_linking`). Only one INSERT needs updating.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: add is_cancellation to GR import aliases, validation, and INSERT"
```

---

### Task 4: bridge.py — download_gr_template

**Files:**
- Modify: `sc_gr_app/api/bridge.py`

- [ ] **Step 1: Add `is_cancellation` to template headers/hints/sample**

In `download_gr_template` (line ~2133), update the three lists:

```python
        headers = ["po_no", "gr_no", "requester_id",
                   "estimated_amount", "con_value", "status", "remark", "tax_rate",
                   "gross_cost", "goods_service_description", "confirmation_name",
                   "delivery_from", "delivery_to", "last_delivery", "is_cancellation"]
        hints = ["Required (PO NO, must exist in DB)",
                 "Required (business NO, must be unique)",
                 "Optional (defaults to importer)",
                 "Required", "Required",
                 "approved/finished", "Optional",
                 "Optional (e.g. 13)", "Optional", "Optional", "Optional",
                 "Required (YYYY-MM-DD or MM/DD/YYYY)", "Required (YYYY-MM-DD or MM/DD/YYYY)", "Optional (YYYY-MM-DD or MM/DD/YYYY)",
                 "Optional (Y/N, default N)"]
        sample = ["", "[EXAMPLE]", current_user["user_id"],
                  "10000", "10000", "approved", "", "13",
                  "", "Sample goods description", "",
                  "2026-01-01", "2026-12-31", "", "N"]
```

- [ ] **Step 2: Update info text to mention is_cancellation**

In the `info_text` (line ~2178), add a note:
```python
        info_text = (
            "Import Rules: Only GR records with status \"approved\" or \"finished\" can be imported. "
            "Required fields: PO NO, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. "
            "Linking: GR is linked to PO via PO NO (not PO ID). "
            "Duplicate GR NOs in database will cause import errors. "
            "is_cancellation: set \"Y\" for Cancellation GR (negative amounts), default \"N\"."
        )
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add is_cancellation column to GR import template download"
```

---

### Task 5: templates.py — email subject and field labels

**Files:**
- Modify: `sc_gr_app/notification/templates.py`

- [ ] **Step 1: Update `_GR_RENAMES` and `_GR_ORDER`**

Add `is_cancellation` to `_GR_RENAMES` (line ~101):
```python
_GR_RENAMES = {
    "estimated_amount": "GR Application Amount (Net)",
    "gross_cost": "GR Application Amount (Gross)",
    "con_value": "GR Value",
    "is_cancellation": "Cancellation GR",
}
```

Add `is_cancellation` to `_GR_ORDER` (line ~118), at the end:
```python
_GR_ORDER = ["gr_id", "gr_no", "po_id", "requester_id",
             "estimated_amount", "gross_cost", "tax_rate", "con_value",
             "goods_service_description", "remark", "confirmation_name",
             "delivery_from", "delivery_to", "last_delivery",
             "is_cancellation"]
```

- [ ] **Step 2: Update `build_subject` to add entity type to subject, with "(Cancellation)" prefix for Cancellation GRs**

Modify `build_subject` (line ~338). This change has **two effects**: (1) all subjects now include entity type (e.g., `GR`, `SC`, `PO`) — previously absent; (2) Cancellation GRs get `(Cancellation) GR` instead of plain `GR`.

```python
def build_subject(entry: dict, entity_info: dict, actor_name: str = "") -> str:
    """Build email subject line.

    Format: [POMP] <action> <short_entity_id> from <name>
    For Cancellation GR: [POMP] <action> (Cancellation) GR <short_entity_id> from <name>
    """
    entity_id = _short_entity_id(entry.get("entity_id", ""))
    event_type = entry.get("event_type", "")
    event_key = entry.get("event_key", "")
    entity_type = entry.get("entity_type", "")

    if event_type == "status_change":
        action = _TRANSITION_LABELS.get(event_key, event_key)
    elif event_type == "threshold_date":
        months = event_key.replace("threshold_date:", "").replace("m", "")
        action = f"Contract Expiring <{months}m"
    elif event_type == "threshold_amount":
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        action = f"Budget Exhausting <{pct}%"
    elif event_type == "custom_schedule":
        action = "Scheduled Reminder"
    else:
        action = event_key

    # Build entity type label with Cancellation prefix if applicable
    type_label = entity_type.upper()
    if entity_type == "gr" and entity_info.get("is_cancellation") == "Y":
        type_label = "(Cancellation) GR"

    abbr = _abbreviate_name(actor_name) if actor_name else "System"
    return f"[POMP] {action} {type_label} {entity_id} from {abbr}"
```

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: add is_cancellation to email fields and (Cancellation) subject prefix"
```

---

### Task 6: Frontend — GrFormDialog.vue

**Files:**
- Modify: `frontend/src/components/po/GrFormDialog.vue`

- [ ] **Step 1: Add `is_cancellation` select field to template**

After the `last_delivery` block (around line ~69) and before the `delivery_from` row, add:

```html
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="$t('gr.isCancellation')">
            <el-select v-model="form.is_cancellation" style="width:100%" @change="onIsCancellationChange">
              <el-option :label="$t('common.no')" value="N" />
              <el-option :label="$t('common.yes')" value="Y" />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
```

- [ ] **Step 2: Update `estimated_amount` input-number with dynamic min/max**

Change line 28 from:
```html
            <el-input-number v-model="form.estimated_amount" :precision="2" :min="0" controls-position="right" style="width:100%" :disabled="isReadOnly" @change="calcInclTax" />
```
To:
```html
            <el-input-number v-model="form.estimated_amount" :precision="2" :min="estimatedAmountMin" :max="estimatedAmountMax" controls-position="right" style="width:100%" :disabled="isReadOnly" @change="calcInclTax" />
```

- [ ] **Step 3: Update `con_value` input-number with dynamic min/max**

Change line 45 from:
```html
            <el-input-number v-model="form.con_value" :precision="2" :min="0" controls-position="right" style="width:100%" />
```
To:
```html
            <el-input-number v-model="form.con_value" :precision="2" :min="conValueMin" :max="conValueMax" controls-position="right" style="width:100%" />
```

- [ ] **Step 4: Update `gross_cost` disabled input-number with dynamic min/max**

Change line 40 from:
```html
            <el-input-number :model-value="computedInclTax" :precision="2" :min="0" controls-position="right" style="width:100%" disabled />
```
To:
```html
            <el-input-number :model-value="computedInclTax" :precision="2" :min="grossCostMin" :max="grossCostMax" controls-position="right" style="width:100%" disabled />
```

- [ ] **Step 5: Add computed properties for dynamic min/max and change handler in `<script>`**

After the `computedInclTax` computed (line ~176), add:

```javascript
const isCancellation = computed(() => form.is_cancellation === 'Y')

const estimatedAmountMin = computed(() => isCancellation.value ? undefined : 0)
const estimatedAmountMax = computed(() => isCancellation.value ? 0 : undefined)
const conValueMin = computed(() => isCancellation.value ? undefined : 0)
const conValueMax = computed(() => isCancellation.value ? 0 : undefined)
const grossCostMin = computed(() => isCancellation.value ? undefined : 0)
const grossCostMax = computed(() => isCancellation.value ? 0 : undefined)

function onIsCancellationChange() {
  // When switching to cancellation, clear positive amounts to avoid confusion
  if (isCancellation.value && form.estimated_amount > 0) {
    form.estimated_amount = null
    form.con_value = null
    form.gross_cost = null
  }
  // When switching back to normal, clear negative amounts
  if (!isCancellation.value && form.estimated_amount < 0) {
    form.estimated_amount = null
    form.con_value = null
    form.gross_cost = null
  }
}
```

- [ ] **Step 6: Add `is_cancellation` to `emptyForm()`**

In `emptyForm()` (line ~166), add `is_cancellation: 'N'`:
```javascript
const emptyForm = () => ({
  gr_no: null, requester_id: '', estimated_amount: null, tax_rate: null,
  con_value: null, gross_cost: null, remark: '',
  pending_date: null, approved_date: null,
  goods_service_description: '', confirmation_name: '',
  delivery_from: null, delivery_to: null, last_delivery: 'N',
  is_cancellation: 'N'
})
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/po/GrFormDialog.vue
git commit -m "feat: add is_cancellation field and dynamic amount constraints to GrFormDialog"
```

---

### Task 7: Frontend — GrDetailView.vue

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue`

- [ ] **Step 1: Add `is_cancellation` display row in template**

Find the `<el-descriptions>` block for GR details (around line ~42). Add after the `last_delivery` row:

```html
          <el-descriptions-item :label="$t('gr.isCancellation')">
            {{ gr.is_cancellation === 'Y' ? $t('common.yes') : $t('common.no') }}
          </el-descriptions-item>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/GrDetailView.vue
git commit -m "feat: display is_cancellation field in GrDetailView"
```

---

### Task 8: Frontend — GrListView.vue

**Files:**
- Modify: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Add `is_cancellation` column to the table**

After the `last_delivery` column (line ~78), add:

```html
      <el-table-column prop="is_cancellation" :label="$t('gr.isCancellation')" width="100" sortable>
        <template #default="{ row }">{{ row.is_cancellation === 'Y' ? $t('common.yes') : $t('common.no') }}</template>
      </el-table-column>
```

- [ ] **Step 2: Add `is_cancellation` to filter definitions**

Find the `filters` array (around line ~276). Add after an existing filter entry:
```javascript
  { name: 'is_cancellation', label: t('gr.isCancellation'), type: 'select', options: [{ label: t('common.yes'), value: 'Y' }, { label: t('common.no'), value: 'N' }] },
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrListView.vue
git commit -m "feat: add is_cancellation column and filter to GrListView"
```

---

### Task 9: Frontend — GrTable.vue

**Files:**
- Modify: `frontend/src/components/po/GrTable.vue`

- [ ] **Step 1: Add `is_cancellation` column to the PO detail GR sub-table**

After the existing `remark` column (GrTable.vue line ~29), add:

```html
    <el-table-column prop="is_cancellation" :label="$t('gr.isCancellation')" width="100" sortable>
      <template #default="{ row }">{{ row.is_cancellation === 'Y' ? $t('common.yes') : $t('common.no') }}</template>
    </el-table-column>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/po/GrTable.vue
git commit -m "feat: add is_cancellation column to GrTable"
```

---

### Task 10: Frontend — ExportDialog.vue

**Files:**
- Modify: `frontend/src/components/export/ExportDialog.vue`

- [ ] **Step 1: Add `is_cancellation` to GR export column definitions**

Find the GR export columns (around line ~164). Add after existing columns:

```javascript
  { key: 'is_cancellation', label: t('gr.isCancellation') },
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/export/ExportDialog.vue
git commit -m "feat: add is_cancellation to GR export columns"
```

---

### Task 11: Frontend — i18n (zh-CN + en-US)

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add translation keys**

In `zh-CN.js`, find the `gr` section and add:
```javascript
    isCancellation: '是否取消类型',
```

In `en-US.js`, find the `gr` section and add:
```javascript
    isCancellation: 'Cancellation GR',
```

- [ ] **Step 2: Verify `common.yes` and `common.no` exist**

These are already used by `last_delivery` — confirm they exist in both locale files. No action needed.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add isCancellation i18n keys for zh-CN and en-US"
```

---

### Task 12: Integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run backend tests**

```bash
cd sc_gr_app && uv run pytest tests/ -v --tb=short
```

Expected: All existing tests pass with the migration applied.

- [ ] **Step 2: Verify migration is idempotent**

```bash
cd sc_gr_app && uv run python -c "
from sc_gr_app.db.migrations import migrate
from sc_gr_app.config import default_config
# Run twice — second run should be no-op
migrate(default_config(is_beta=False))
migrate(default_config(is_beta=False))
print('Migration is idempotent')
"
```

- [ ] **Step 3: Manual smoke test checklist**

1. Create a Cancellation GR: Set `is_cancellation='Y'`, enter negative amount → should save
2. Verify amount constraint: Try positive amount with `is_cancellation='Y'` → should reject
3. Verify budget skip: Cancellation GR submit/approve should not check budget
4. Approve Cancellation GR: Enter negative con_value → should approve
5. Email notification: Check subject contains "(Cancellation) GR"
6. Import: Import a GR with `is_cancellation='Y'` and negative amounts → should succeed
7. Export: Export GR list → `is_cancellation` column should appear
8. List/Dashboard: Negative amounts display correctly in AmountDisplay

- [ ] **Step 4: Commit any remaining changes**

```bash
git status
# If any uncommitted changes, commit them
```
