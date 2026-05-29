# Core Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix broken CRUD operations, auto-generate entity IDs, align form validation, enhance search filters, and fix notification multi-select.

**Architecture:** Backend (Python services) generates IDs and provides range-based filtering; frontend (Vue 3 composables/views/forms) is fixed to send correct payloads, expose all filter fields, and handle GR approve with con_value input.

**Tech Stack:** Python 3.11, SQLite, Vue 3 + Element Plus + Vite, pywebview

---

### Task 1: Backend — ID Auto-Generation in Services

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`
- Modify: `sc_gr_app/services/po_service.py`
- Modify: `sc_gr_app/services/gr_service.py`

- [ ] **Step 1: Add `_generate_sc_id()` and update `create_sc_draft()` in sc_service.py**

Add the generator function after `utc_now()` (line 48):

```python
def _generate_sc_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"SC-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT sc_id FROM sc_records WHERE sc_id LIKE ? ORDER BY sc_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["sc_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"SC-{machine_id}-{today}-{seq:03d}"
```

Update `REQUIRED_FIELDS` (line 18) — remove `"sc_id"`:

```python
REQUIRED_FIELDS = (
    "requester_id",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
)
```

Update `create_sc_draft` (line 275) — replace `sc_id = data["sc_id"]` with auto-generation:

```python
def create_sc_draft(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, ("requester_id",))
    if (
        current_user["role"] == "requester"
        and data["requester_id"] != current_user["user_id"]
    ):
        raise PermissionDenied("Requester can only create their own draft SC")

    timestamp = utc_now()
    sc_id = _generate_sc_id(config, current_user["machine_id"])

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        # ... rest unchanged
```

Update `create_sc` (line 185) — same replacement, remove `sc_id = data["sc_id"]`:

```python
def create_sc(config, current_user, data, operation_mode="normal"):
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    # ... validation unchanged ...

    timestamp = utc_now()
    sc_id = _generate_sc_id(config, current_user["machine_id"])
    # ... rest unchanged
```

- [ ] **Step 2: Add `_generate_po_id()` and update `create_po()` in po_service.py**

Add generator:

```python
def _generate_po_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"PO-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT po_id FROM pos WHERE po_id LIKE ? ORDER BY po_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["po_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"PO-{machine_id}-{today}-{seq:03d}"
```

Update `REQUIRED_FIELDS` — remove `"po_id"`:

```python
REQUIRED_FIELDS = ("sc_id", "vendor_id", "po_amount")
```

Update `create_po` — replace `po_id = data["po_id"]`:

```python
def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    # ... validation unchanged ...
    timestamp = utc_now()
    po_id = _generate_po_id(config, current_user["machine_id"])
    # ... rest unchanged
```

- [ ] **Step 3: Add `_generate_gr_id()` and update `create_gr()` in gr_service.py**

Add generator:

```python
def _generate_gr_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"GR-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT gr_id FROM gr_requests WHERE gr_id LIKE ? ORDER BY gr_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["gr_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"GR-{machine_id}-{today}-{seq:03d}"
```

Update `REQUIRED_FIELDS` — remove `"gr_id"`:

```python
REQUIRED_FIELDS = ("po_id", "requester_id", "estimated_amount")
```

Update `create_gr` — replace `gr_id = data["gr_id"]`:

```python
def create_gr(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    # ... validation unchanged ...
    timestamp = utc_now()
    gr_id = _generate_gr_id(config, current_user["machine_id"])
    # ... rest unchanged
```

- [ ] **Step 4: Run existing tests**

```
uv run pytest tests/ -q
```
Expected: all existing tests pass (REQUIRED_FIELDS removal shouldn't break existing tests since tests provide IDs through data dict).

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/sc_service.py sc_gr_app/services/po_service.py sc_gr_app/services/gr_service.py
git commit -m "feat: auto-generate SC/PO/GR IDs with machine-prefixed timestamp format"
```

---

### Task 2: Backend — Range Filter Support in query_service.py

**Files:**
- Modify: `sc_gr_app/services/query_service.py`

- [ ] **Step 1: Modify `_append_filters()` to support range suffixes**

Replace the existing `_append_filters` function (lines 64-77):

```python
def _append_filters(
    clauses: list[str],
    params: list,
    filters: dict | None,
    allowed_filters: dict[str, str],
) -> None:
    if not filters:
        return
    for field, value in filters.items():
        if value is None or value == "":
            continue
        if field.endswith("_from"):
            base = field[:-5]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} >= ?")
            params.append(value)
        elif field.endswith("_to"):
            base = field[:-3]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} <= ?")
            params.append(value)
        elif field.endswith("_min"):
            base = field[:-4]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} >= ?")
            params.append(value)
        elif field.endswith("_max"):
            base = field[:-4]
            column = allowed_filters.get(base)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} <= ?")
            params.append(value)
        else:
            column = allowed_filters.get(field)
            if column is None:
                raise ValidationError("filter field is invalid")
            clauses.append(f"{column} = ?")
            params.append(value)
```

- [ ] **Step 2: Complete allowed_filters for all entities**

Replace each `allowed_filters` dict in the search functions:

**search_scs** (line 179):
```python
allowed_filters={
    "sc_id": "sc.sc_id",
    "sc_no": "sc.sc_no",
    "requester_id": "sc.requester_id",
    "request_type": "sc.request_type",
    "cost_center": "sc.cost_center",
    "status": "sc.status",
    "created_by": "sc.created_by",
    "sc_amount": "sc.sc_amount",
    "sc_amount_min": "sc.sc_amount",
    "sc_amount_max": "sc.sc_amount",
    "service_period_start": "sc.service_period_start",
    "service_period_start_from": "sc.service_period_start",
    "service_period_start_to": "sc.service_period_start",
    "service_period_end": "sc.service_period_end",
    "service_period_end_from": "sc.service_period_end",
    "service_period_end_to": "sc.service_period_end",
    "description": "sc.description",
    "created_at": "sc.created_at",
    "created_at_from": "sc.created_at",
    "created_at_to": "sc.created_at",
    "updated_at": "sc.updated_at",
    "approved_by": "sc.approved_by",
    "approved_at": "sc.approved_at",
    "closed_at": "sc.closed_at",
},
```

**search_pos** (line 298):
```python
allowed_filters={
    "po_id": "po.po_id",
    "po_no": "po.po_no",
    "sc_id": "po.sc_id",
    "vendor_id": "po.vendor_id",
    "status": "po.status",
    "vendor_name": "vendor.vendor_name",
    "po_amount": "po.po_amount",
    "po_amount_min": "po.po_amount",
    "po_amount_max": "po.po_amount",
    "contract_from": "po.contract_from",
    "contract_from_from": "po.contract_from",
    "contract_from_to": "po.contract_from",
    "contract_to": "po.contract_to",
    "contract_to_from": "po.contract_to",
    "contract_to_to": "po.contract_to",
    "contract_no": "po.contract_no",
    "payment_frequency": "po.payment_frequency",
    "created_at": "po.created_at",
    "updated_at": "po.updated_at",
},
```

**search_grs** (line 362):
```python
allowed_filters={
    "gr_id": "gr.gr_id",
    "po_id": "gr.po_id",
    "requester_id": "gr.requester_id",
    "status": "gr.status",
    "sc_id": "po.sc_id",
    "vendor_id": "vendor.vendor_id",
    "estimated_amount": "gr.estimated_amount",
    "estimated_amount_min": "gr.estimated_amount",
    "estimated_amount_max": "gr.estimated_amount",
    "con_value": "gr.con_value",
    "con_value_min": "gr.con_value",
    "con_value_max": "gr.con_value",
    "remark": "gr.remark",
    "created_by": "gr.created_by",
    "created_at": "gr.created_at",
    "created_at_from": "gr.created_at",
    "created_at_to": "gr.created_at",
    "approved_by": "gr.approved_by",
    "approved_at": "gr.approved_at",
    "cancelled_by": "gr.cancelled_by",
    "cancelled_at": "gr.cancelled_at",
},
```

**search_vendors** (line 231):
```python
allowed_filters={
    "vendor_id": "vendor_id",
    "vendor_name": "vendor_name",
    "ksrm_vendor_code": "ksrm_vendor_code",
    "service_scope": "service_scope",
    "created_by": "created_by",
    "contact_person": "contact_person",
    "email": "email",
    "phone": "phone",
    "description": "description",
    "status": "status",
    "created_at": "created_at",
    "updated_at": "updated_at",
},
```

Also update `text_columns` in each function to match — add the new columns to the text search tuples.

**search_scs text_columns** add: `"cast(sc.sc_amount as text)"`, `"sc.service_period_start"`, `"sc.service_period_end"`, `"sc.created_at"`, `"sc.approved_at"`, `"sc.approved_by"`

**search_pos text_columns** add: `"cast(po.po_amount as text)"`, `"po.contract_from"`, `"po.contract_to"`, `"po.created_at"`

**search_grs text_columns** add: `"cast(gr.estimated_amount as text)"`, `"cast(gr.con_value as text)"`, `"gr.created_at"`, `"gr.created_by"`, `"gr.approved_by"`

**search_vendors text_columns** add: `"phone"`, `"status"`, `"created_at"`

- [ ] **Step 3: Run existing query tests**

```
uv run pytest tests/ -q -k "search"
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "feat: add range filter operators (_from/_to/_min/_max) and complete all allowed_filters and text_columns"
```

---

### Task 3: Backend — Tests for ID Generation and Range Filters

**Files:**
- Modify: `tests/test_sc_service.py`
- Modify: `tests/test_po_service.py`
- Modify: `tests/test_gr_service.py`
- Modify: `tests/test_query_service.py`

- [ ] **Step 1: Add ID generation tests**

Check if these test files exist, then add tests:

```python
# In test_sc_service.py (or create tests/test_id_generation.py)
from sc_gr_app.services.sc_service import _generate_sc_id
from sc_gr_app.services.po_service import _generate_po_id
from sc_gr_app.services.gr_service import _generate_gr_id

def test_generate_sc_id_creates_sequential_ids(app_config):
    mid = "TESTUSR"
    id1 = _generate_sc_id(app_config, mid)
    # Manually insert to simulate prior record
    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, status) VALUES (?, ?, 'draft')",
            (id1, "U-001"),
        )
        conn.commit()
    id2 = _generate_sc_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"SC-{mid}-")

def test_generate_po_id_creates_sequential_ids(app_config):
    mid = "TESTUSR"
    id1 = _generate_po_id(app_config, mid)
    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        conn.execute("INSERT INTO sc_records (sc_id, requester_id, status) VALUES ('SC-001', 'U-001', 'approved')")
        conn.commit()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO pos (po_id, sc_id, vendor_id, po_amount, status) VALUES (?, 'SC-001', 'V-001', 100, 'po_pending')",
            (id1,),
        )
        conn.commit()
    id2 = _generate_po_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"PO-{mid}-")

def test_generate_gr_id_creates_sequential_ids(app_config):
    mid = "TESTUSR"
    id1 = _generate_gr_id(app_config, mid)
    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        conn.execute("INSERT INTO sc_records (sc_id, requester_id, status) VALUES ('SC-GR', 'U-001', 'approved')")
        conn.execute("INSERT INTO pos (po_id, sc_id, vendor_id, po_amount, status) VALUES ('PO-GR', 'SC-GR', 'V-001', 100, 'po_approved')")
        conn.commit()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO gr_requests (gr_id, po_id, requester_id, estimated_amount, status) VALUES (?, 'PO-GR', 'U-001', 50, 'pending')",
            (id1,),
        )
        conn.commit()
    id2 = _generate_gr_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"GR-{mid}-")
```

- [ ] **Step 2: Add range filter tests**

```python
# In test_query_service.py
def test_filter_with_range_suffixes(app_config):
    from sc_gr_app.services.query_service import search_scs
    from sc_gr_app.db.connection import connect
    from datetime import datetime, timezone

    timestamp = datetime.now(timezone.utc).isoformat()
    with connect(app_config) as conn:
        conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U-1', 'M1', 'u1', 'admin', 'active', ?, ?)", (timestamp, timestamp))
        conn.execute("INSERT INTO sc_records (sc_id, requester_id, sc_amount, status, created_at, updated_at) VALUES ('SC-A', 'U-1', 100, 'pending', '2026-01-01', ?)", (timestamp,))
        conn.execute("INSERT INTO sc_records (sc_id, requester_id, sc_amount, status, created_at, updated_at) VALUES ('SC-B', 'U-1', 200, 'approved', '2026-06-01', ?)", (timestamp,))
        conn.commit()

    # Range filter: sc_amount_min
    results = search_scs(app_config, filters={"sc_amount_min": 150}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-B"

    # Range filter: sc_amount_max
    results = search_scs(app_config, filters={"sc_amount_max": 150}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-A"

    # Date range
    results = search_scs(app_config, filters={"service_period_start_from": "2026-03-01"}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-B"
```

- [ ] **Step 3: Run tests**

```
uv run pytest tests/ -q -k "generate_id or range"
```
Expected: all new tests pass.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: add tests for ID generation and range filter operators"
```

---

### Task 4: Frontend — Fix Composable API Signatures

**Files:**
- Modify: `frontend/src/composables/useSc.js`
- Modify: `frontend/src/composables/usePo.js`
- Modify: `frontend/src/composables/useGr.js`

- [ ] **Step 1: Fix useSc.js**

Change the `submitSc` and `updateSc` signatures (lines 60-66):

```javascript
async function submitSc(scId, data) {
    return await callApi('submit_sc', { sc_id: scId, data })
}

async function updateSc(scId, data) {
    return await callApi('update_sc', { sc_id: scId, data })
}
```

- [ ] **Step 2: Fix usePo.js**

Change `updatePo` signature (line 41):

```javascript
async function updatePo(poId, data) { return await callApi('update_po', { po_id: poId, data }) }
```

- [ ] **Step 3: Fix useGr.js**

Change `updateGr` and `approveGr` signatures (lines 41-42):

```javascript
async function updateGr(grId, data) { return await callApi('update_gr', { gr_id: grId, data }) }
async function approveGr(grId, conValue) { await callApi('approve_gr', { gr_id: grId, con_value: conValue }) }
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/composables/useSc.js frontend/src/composables/usePo.js frontend/src/composables/useGr.js
git commit -m "fix: standardize composable API signatures to match bridge payload expectations"
```

---

### Task 5: Frontend — Fix Form Dialogs (Remove ID, Align Rules)

**Files:**
- Modify: `frontend/src/components/sc/ScFormDialog.vue`
- Modify: `frontend/src/components/po/PoFormDialog.vue`
- Modify: `frontend/src/components/po/GrFormDialog.vue`

- [ ] **Step 1: Fix ScFormDialog.vue**

Remove the SC ID input from template (lines 11-13):
```html
<!-- DELETE these lines -->
<el-col :span="12">
  <el-form-item label="SC ID" prop="sc_id">
    <el-input v-model="form.sc_id" :disabled="mode === 'edit'" />
  </el-form-item>
</el-col>
```

The first row should become just SC No taking full width or keep the 2-col layout with only SC No.

Remove `sc_id` from `emptyForm()` (line 93):
```javascript
const emptyForm = () => ({
  sc_no: '',
  requester_id: '',
  request_type: '',
  cost_center: '',
  sc_amount: null,
  service_period_start: null,
  service_period_end: null,
  description: ''
})
```

Replace `rules` with two rule sets based on mode (line 106):
```javascript
const draftRules = {
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'change' }]
}
const submitRules = {
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'change' }],
  request_type: [{ required: true, message: 'Request Type is required', trigger: 'change' }],
  cost_center: [{ required: true, message: 'Cost Center is required', trigger: 'blur' }],
  sc_amount: [{ required: true, message: 'SC Amount is required', trigger: 'blur' }],
  service_period_start: [{ required: true, message: 'Service Period Start is required', trigger: 'change' }],
  service_period_end: [{ required: true, message: 'Service Period End is required', trigger: 'change' }]
}
```

Update `saveSubmit` to use `submitRules`:
```javascript
async function saveSubmit() {
  if (!formRef.value) return
  // Temporarily swap to submit rules for validation
  formRef.value.clearValidate()
  try {
    await formRef.value.validate((valid) => {
      if (!valid) return false
    })
  } catch { return }
  submitting.value = true
  try {
    emit('save-submit', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
```

Use a simpler approach — bind `rules` to a computed that switches based on which button is pressed:

In `<script setup>`, replace the `rules` const with a reactive state:
```javascript
const rules = reactive({ ...draftRules })

async function saveDraft() {
  submitting.value = true
  try {
    emit('save-draft', { ...form })
    emit('update:visible', false)
    ElMessage.success('Draft saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}

async function saveSubmit() {
  if (!formRef.value) return
  // Switch to full rules
  Object.assign(rules, submitRules)
  try {
    await formRef.value.validate()
  } catch { return }
  submitting.value = true
  try {
    emit('save-submit', { ...form })
    emit('update:visible', false)
    ElMessage.success('Saved')
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    submitting.value = false
  }
}
```

Reset rules to draftRules when dialog opens:
```javascript
watch(() => props.visible, (val) => {
  if (val && props.mode === 'edit' && props.record) {
    Object.assign(form, props.record)
    Object.assign(rules, submitRules)  // edit mode always has full validation
  } else if (val) {
    Object.assign(form, emptyForm())
    Object.assign(rules, draftRules)
  }
})
```

- [ ] **Step 2: Fix PoFormDialog.vue**

Remove PO ID input from template (lines 11-13):
```html
<!-- DELETE -->
<el-col :span="12">
  <el-form-item label="PO ID" prop="po_id">
    <el-input v-model="form.po_id" :disabled="mode === 'edit'" />
  </el-form-item>
</el-col>
```

Remove `po_id` from `emptyForm()`:
```javascript
const emptyForm = () => ({
  po_no: '', vendor_id: '', po_amount: null,
  contract_from: null, contract_to: null, contract_no: '', payment_frequency: ''
})
```

Replace `rules`:
```javascript
const rules = {
  vendor_id: [{ required: true, message: 'Vendor is required', trigger: 'change' }],
  po_amount: [{ required: true, message: 'PO Amount is required', trigger: 'blur' }]
}
```

- [ ] **Step 3: Fix GrFormDialog.vue**

Remove GR ID input from template (lines 11-13):
```html
<!-- DELETE -->
<el-col :span="12">
  <el-form-item label="GR ID" prop="gr_id">
    <el-input v-model="form.gr_id" :disabled="mode === 'edit'" />
  </el-form-item>
</el-col>
```

Remove `gr_id` from `emptyForm()`:
```javascript
const emptyForm = () => ({
  requester_id: '', estimated_amount: null, con_value: null, remark: ''
})
```

Replace `rules`:
```javascript
const rules = {
  requester_id: [{ required: true, message: 'Requester is required', trigger: 'blur' }],
  estimated_amount: [{ required: true, message: 'Estimated Amount is required', trigger: 'blur' }]
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/sc/ScFormDialog.vue frontend/src/components/po/PoFormDialog.vue frontend/src/components/po/GrFormDialog.vue
git commit -m "fix: remove ID input fields from forms, align required field rules with backend"
```

---

### Task 6: Frontend — Fix View Call Sites

**Files:**
- Modify: `frontend/src/views/ScListView.vue`
- Modify: `frontend/src/views/ScDetailView.vue`
- Modify: `frontend/src/views/PoDetailView.vue`

- [ ] **Step 1: Fix ScListView.vue handleSaveSubmit and handleSaveDraft**

Update `handleSaveDraft` (line 98) — remove `sc_id` from data (backend generates it now):
```javascript
async function handleSaveDraft(data) {
  try {
    await createDraft(data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}
```

Update `handleSaveSubmit` (line 108) — call `submitSc(scId, data)` with correct args:
```javascript
async function handleSaveSubmit(data) {
  try {
    // For new SC, first create draft, then submit
    const created = await createDraft(data)
    await submitSc(created.sc_id, data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}
```

Wait — the `handleSaveSubmit` flow: in ScListView, the user clicks "Submit" which should create a draft then immediately submit it. Actually looking at the current code, `handleSaveSubmit` directly calls `submitSc(data)`. But submit expects an existing draft SC. The flow should be: create draft → get generated sc_id → submit. Let me fix this properly:

```javascript
async function handleSaveSubmit(data) {
  try {
    const created = await createDraft(data)
    await submitSc(created.sc_id, data)
    await searchScs()
  } catch (e) {
    ElMessage.error(e.message)
    throw e
  }
}
```

- [ ] **Step 2: Fix ScDetailView.vue handleSubmit and handleEditSave**

Update `handleSubmit` (line 137) — pass sc_id and empty data (bridge merges with before):
```javascript
async function handleSubmit() {
  try {
    await ElMessageBox.confirm('Submit this SC?', 'Confirm', { type: 'warning' })
    await submitSc(scId.value, {})
    ElMessage.success('SC submitted')
    await fetchDetail(scId.value)
  } catch { /* cancelled */ }
}
```

Update `handleEditSave` (line 129) — pass sc_id and form data:
```javascript
async function handleEditSave(data) {
  try {
    await updateSc(data.sc_id || scId.value, data)
    ElMessage.success('SC updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}
```

Update `handlePoSave` (line 196) — pass po_id for updates:
```javascript
async function handlePoSave(data) {
  try {
    if (poDialogMode.value === 'create') {
      await createPo({ ...data, sc_id: scId.value })
    } else {
      await updatePo(data.po_id, data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    poDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}
```

- [ ] **Step 3: Fix PoDetailView.vue**

Update `handleEditSave` (line 108):
```javascript
async function handleEditSave(data) {
  try {
    await updatePo(data.po_id || poId.value, data)
    ElMessage.success('PO updated')
    await fetchDetail(scId.value)
  } catch (e) { ElMessage.error(e.message); throw e }
}
```

Update `handleGrApprove` (line 134) — add con_value prompt:
```javascript
async function handleGrApprove(row) {
  try {
    const { value } = await ElMessageBox.prompt(
      'Enter contract value (con_value) for this GR:',
      'Approve GR',
      {
        confirmButtonText: 'Approve',
        type: 'warning',
        inputPattern: /^\d+(\.\d{1,2})?$/,
        inputErrorMessage: 'Enter a valid positive number'
      }
    )
    await approveGr(row.gr_id, parseFloat(value))
    ElMessage.success('GR approved')
    await fetchDetail(scId.value)
  } catch {}
}
```

Update `handleGrSave` (line 152):
```javascript
async function handleGrSave(data) {
  try {
    if (grDialogMode.value === 'create') {
      await createGr({ ...data, po_id: poId.value })
    } else {
      await updateGr(data.gr_id, data)
    }
    ElMessage.success('Saved')
    await fetchDetail(scId.value)
    grDialogVisible.value = false
  } catch (e) { ElMessage.error(e.message); throw e }
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/ScDetailView.vue frontend/src/views/PoDetailView.vue
git commit -m "fix: update view call sites to match new composable signatures and ID auto-generation"
```

---

### Task 7: Frontend — Build AdvancedFilterBar Component

**Files:**
- Create: `frontend/src/components/common/AdvancedFilterBar.vue`
- Delete: `frontend/src/components/common/FilterBar.vue` (replaced)

- [ ] **Step 1: Create AdvancedFilterBar.vue**

```vue
<template>
  <div class="filter-bar">
    <div class="filter-controls">
      <el-input
        v-model="searchText"
        placeholder="Search all fields..."
        :prefix-icon="Search"
        clearable
        style="width: 260px"
        @input="onSearchDebounced"
      />
      <el-button
        text
        type="primary"
        @click="showAdvanced = !showAdvanced"
      >
        {{ showAdvanced ? 'Hide' : 'Advanced' }} Filters
      </el-button>
    </div>
    <div class="filter-actions">
      <slot name="actions" />
    </div>

    <div v-if="showAdvanced" class="advanced-filters">
      <template v-for="f in filterConfig" :key="f.name">
        <!-- Select filter -->
        <el-select
          v-if="f.type === 'select'"
          v-model="filterValues[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @change="emitFilters"
        >
          <el-option
            v-for="opt in f.options"
            :key="opt.value"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>

        <!-- Input filter -->
        <el-input
          v-else-if="f.type === 'input'"
          v-model="filterValues[f.name]"
          :placeholder="f.label"
          clearable
          style="width: 160px"
          @change="emitFilters"
        />

        <!-- Date range filter -->
        <template v-else-if="f.type === 'date-range'">
          <el-date-picker
            v-model="filterValues[f.name + '_from']"
            :placeholder="f.label + ' from'"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @change="emitFilters"
          />
          <el-date-picker
            v-model="filterValues[f.name + '_to']"
            :placeholder="f.label + ' to'"
            type="date"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 160px"
            @change="emitFilters"
          />
        </template>

        <!-- Amount range filter -->
        <template v-else-if="f.type === 'amount-range'">
          <el-input-number
            v-model="filterValues[f.name + '_min']"
            :placeholder="f.label + ' min'"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @change="emitFilters"
          />
          <el-input-number
            v-model="filterValues[f.name + '_max']"
            :placeholder="f.label + ' max'"
            :precision="2"
            :min="0"
            controls-position="right"
            style="width: 160px"
            @change="emitFilters"
          />
        </template>
      </template>

      <el-button @click="handleReset">Reset</el-button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
import { Search } from '@element-plus/icons-vue'

const props = defineProps({
  filterConfig: { type: Array, default: () => [] }
})

const emit = defineEmits(['filter', 'reset'])

const searchText = ref('')
const showAdvanced = ref(false)
const filterValues = reactive({})

let debounceTimer = null

function onSearchDebounced() {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    emitFilters()
  }, 500)
}

function emitFilters() {
  const filters = {}
  for (const [key, value] of Object.entries(filterValues)) {
    if (value !== null && value !== '' && value !== undefined) {
      filters[key] = value
    }
  }
  emit('filter', { text: searchText.value || null, filters })
}

function handleReset() {
  searchText.value = ''
  for (const key of Object.keys(filterValues)) {
    delete filterValues[key]
  }
  emit('reset')
}
</script>

<style scoped>
.filter-bar { padding: 12px 16px; background: #fff; border-radius: 4px; margin-bottom: 12px; }
.filter-controls { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }
.filter-actions { display: flex; gap: 8px; flex-shrink: 0; }
.advanced-filters { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-top: 8px; border-top: 1px solid #e5e7eb; }
</style>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/common/AdvancedFilterBar.vue
git commit -m "feat: add AdvancedFilterBar component with text search, date/amount range, and expandable filters"
```

---

### Task 8: Frontend — Apply AdvancedFilterBar to List Views

**Files:**
- Modify: `frontend/src/views/ScListView.vue`
- Modify: `frontend/src/views/PoListView.vue`
- Modify: `frontend/src/views/GrListView.vue`
- Modify: `frontend/src/views/VendorListView.vue`
- Modify: `frontend/src/views/LogsView.vue`

- [ ] **Step 1: Fix ScListView.vue filter config**

Replace the `FilterBar` usage with `AdvancedFilterBar`. In the template, replace:

```html
<FilterBar @reset="handleReset">
  <template #filters>
    <el-select v-model="filters.status" placeholder="Status" clearable @change="onFilterChange">
      <el-option v-for="s in scStatuses" :key="s.value" :label="s.label" :value="s.value" />
    </el-select>
    <el-select v-model="filters.request_type" placeholder="Request Type" clearable @change="onFilterChange">
      <el-option v-for="t in requestTypes" :key="t" :label="t" :value="t" />
    </el-select>
    <el-input v-model="filters.cost_center" placeholder="Cost Center" clearable @change="onFilterChange" style="width:150px" />
  </template>
  <template #actions>
    <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
      <el-icon><Plus /></el-icon> New SC
    </el-button>
  </template>
</FilterBar>
```

With:

```html
<AdvancedFilterBar
  :filter-config="scFilterConfig"
  @filter="handleFilter"
  @reset="handleReset"
>
  <template #actions>
    <el-button type="primary" @click="scDialogVisible = true; scDialogMode = 'create'">
      <el-icon><Plus /></el-icon> New SC
    </el-button>
  </template>
</AdvancedFilterBar>
```

In `<script setup>`, remove the `reactive` filters object and replace with filter config:

```javascript
const scFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: scStatuses },
  { name: 'request_type', label: 'Request Type', type: 'select', options: requestTypes.map(t => ({ label: t, value: t })) },
  { name: 'cost_center', label: 'Cost Center', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'sc_no', label: 'SC No', type: 'input' },
  { name: 'requester_id', label: 'Requester', type: 'input' },
  { name: 'created_by', label: 'Created By', type: 'input' },
  { name: 'service_period_start', label: 'Service Start', type: 'date-range' },
  { name: 'sc_amount', label: 'SC Amount', type: 'amount-range' },
]
```

Remove `filters` reactive, `onFilterChange`, and update handlers:

```javascript
const { state, searchScs, createDraft, submitSc, setFilters, resetFilters, onSortChange, onPageChange, onPageSizeChange } = useSc()

function handleFilter({ text, filters }) {
  searchScs(text, filters)
}

function handleReset() {
  resetFilters()
  searchScs()
}
```

- [ ] **Step 2: Fix PoListView.vue**

Similar pattern. Replace FilterBar with AdvancedFilterBar and add poFilterConfig:

```javascript
const poFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: poStatuses },
  { name: 'po_id', label: 'PO ID', type: 'input' },
  { name: 'po_no', label: 'PO No', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'vendor_id', label: 'Vendor ID', type: 'input' },
  { name: 'vendor_name', label: 'Vendor Name', type: 'input' },
  { name: 'po_amount', label: 'PO Amount', type: 'amount-range' },
  { name: 'contract_from', label: 'Contract From', type: 'date-range' },
  { name: 'contract_to', label: 'Contract To', type: 'date-range' },
]
```

- [ ] **Step 3: Fix GrListView.vue**

Replace FilterBar with AdvancedFilterBar and add grFilterConfig. Remove the client-side `filteredRows` computed and client-side amount filters — backend handles this now:

```javascript
const grFilterConfig = [
  { name: 'status', label: 'Status', type: 'select', options: grStatuses },
  { name: 'gr_id', label: 'GR ID', type: 'input' },
  { name: 'po_id', label: 'PO ID', type: 'input' },
  { name: 'sc_id', label: 'SC ID', type: 'input' },
  { name: 'requester_id', label: 'Requester', type: 'input' },
  { name: 'vendor_id', label: 'Vendor ID', type: 'input' },
  { name: 'estimated_amount', label: 'Est. Amount', type: 'amount-range' },
  { name: 'con_value', label: 'Con Value', type: 'amount-range' },
]
```

Use `state.rows` directly instead of `filteredRows`.

- [ ] **Step 4: Fix VendorListView.vue**

Add AdvancedFilterBar with vendorFilterConfig.

- [ ] **Step 5: Fix LogsView.vue**

Add AdvancedFilterBar with audit log filter config.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/PoListView.vue frontend/src/views/GrListView.vue frontend/src/views/VendorListView.vue frontend/src/views/LogsView.vue
git commit -m "feat: apply AdvancedFilterBar to all list views with full field filter support"
```

---

### Task 9: Frontend — Notification Multi-Select Fix

**Files:**
- Modify: `frontend/src/components/notification/ScNotificationCard.vue`
- Modify: `frontend/src/components/notification/NotificationDefaults.vue`

- [ ] **Step 1: Fix ScNotificationCard.vue — add teleported="false"**

Add `:teleported="false"` to the `el-select` (line 11):

```html
<el-select
  v-model="local.cc_user_ids"
  multiple
  filterable
  :teleported="false"
  placeholder="Select users to CC"
  style="width:100%"
  @change="emitSave"
>
```

- [ ] **Step 2: Fix NotificationDefaults.vue — add teleported="false" to all el-select**

Add `:teleported="false"` to all 6 `el-select` instances:
- Line 11: Admin Recipients select
- Line 34: SC transitions "To" select
- Line 43: SC transitions "CC" select
- Plus PO and GR transition selects (2 each in the table columns)

For each `el-select` in the component, add `:teleported="false"`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/notification/ScNotificationCard.vue frontend/src/components/notification/NotificationDefaults.vue
git commit -m "fix: add teleported=false to notification multi-select components"
```

---

### Task 10: Cleanup and Final Verification

**Files:**
- Delete: `frontend/src/components/common/FilterBar.vue` (no longer used)

- [ ] **Step 1: Remove old FilterBar.vue**

```bash
git rm frontend/src/components/common/FilterBar.vue
```

- [ ] **Step 2: Run full test suite**

```
uv run pytest tests/ -q
```
Expected: all tests pass.

- [ ] **Step 3: Build frontend to verify no compilation errors**

```
cd frontend && npm run build
```
Expected: build succeeds with no errors.

- [ ] **Step 4: Run the app and verify**

```
uv run python -m sc_gr_app.main
```

Manual verification checklist:
- [ ] Create SC draft (no SC ID field, auto-generated)
- [ ] Submit SC (fills required fields, submits with correct payload)
- [ ] Approve SC
- [ ] Create PO under approved SC (no PO ID field)
- [ ] Approve PO
- [ ] Create GR under approved PO (no GR ID field)
- [ ] Approve GR (prompted for con_value)
- [ ] Edit SC/PO/GR (update payload includes entity ID)
- [ ] AdvancedFilterBar on all list views — text search and all fields filterable
- [ ] Date range filter returns correct results
- [ ] Amount range filter returns correct results
- [ ] Notification CC multi-select works (can select multiple users)
- [ ] Notification thresholds checkbox group works

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore: remove old FilterBar component, final cleanup"
```
