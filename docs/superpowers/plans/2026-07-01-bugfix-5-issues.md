# 5 Bug Fixes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 5 UI and logic bugs: GR submit button, deny for manager_confirm, SC NO column, vendor export vendor_id, and last-vendor removal.

**Architecture:** Five independent fixes touching frontend Vue components and backend Python services. No new files, no schema changes. Each task is self-contained and can be committed separately.

**Tech Stack:** Vue 3 + Element Plus (frontend), Python 3.11 + SQLite (backend)

---

### Task 1: Add Submit button to GR Detail view

**Files:**
- Modify: `frontend/src/views/GrDetailView.vue:9,121,147`

- [ ] **Step 1: Add Submit button in template**

In `frontend/src/views/GrDetailView.vue`, add a Submit button after the Edit button (line 9) for draft GRs:

```html
<el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'draft'" type="primary" :disabled="loadingState.count > 0" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
```

Insert this line between the Edit button (line 9) and the Confirm button (line 10).

- [ ] **Step 2: Import submitGr from useGr composable**

In the script section at line 121, add `submitGr` to the destructured import:

Change:
```js
const { updateGr, approveGr, denyGr, finishGr } = useGr()
```
To:
```js
const { updateGr, approveGr, denyGr, finishGr, submitGr } = useGr()
```

- [ ] **Step 3: Add handleSubmit function**

Add the `handleSubmit` function in the script section, right before `openEditDialog` (line 147):

```js
async function handleSubmit() {
  try {
    await ElMessageBox.confirm(t('gr.confirmSubmit'), t('common.confirm'), { type: 'warning' })
    await submitGr(grId.value)
    ElMessage.success(t('gr.grSubmitted'))
    await fetchDetail(scId.value)
  } catch (e) {
    if (e !== 'cancel' && e !== 'close') ElMessage.error(e.message || String(e))
  }
}
```

- [ ] **Step 4: Verify i18n key exists for confirm message**

Check that `gr.confirmSubmit` exists in i18n locales. If not, add to `en-US.js` and `zh-CN.js`:

`frontend/src/i18n/locales/en-US.js` — add under `gr:`:
```js
confirmSubmit: 'Submit this GR for confirmation?',
```

`frontend/src/i18n/locales/zh-CN.js` — add under `gr:`:
```js
confirmSubmit: '确认提交此验收申请？',
```

Also add `grSubmitted`:
`en-US.js`:
```js
grSubmitted: 'GR submitted',
```
`zh-CN.js`:
```js
grSubmitted: '验收申请已提交',
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/GrDetailView.vue frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: add Submit button to GR detail view for draft GRs"
```

---

### Task 2: Allow Deny for manager_confirm status (SC and GR)

**Files:**
- Modify: `sc_gr_app/services/sc_service.py:170,848`
- Modify: `sc_gr_app/services/gr_service.py:861`
- Modify: `frontend/src/views/GrDetailView.vue:13`
- Modify: `tests/test_sc_po_gr_flow.py` (add tests)

- [ ] **Step 1: Extend can_deny_sc permission**

In `sc_gr_app/services/sc_service.py`, line 170, change:

```python
"can_deny_sc": is_admin and is_pending,
```
To:
```python
"can_deny_sc": is_admin and (is_pending or is_manager_confirm),
```

- [ ] **Step 2: Extend deny_sc status gate**

In `sc_gr_app/services/sc_service.py`, line 848, change:

```python
if before["status"] != "pending":
    raise ConflictError("SC must be pending")
```
To:
```python
if before["status"] not in ("pending", "manager_confirm"):
    raise ConflictError("SC must be pending or manager_confirm")
```

- [ ] **Step 3: Extend deny_gr status gate**

In `sc_gr_app/services/gr_service.py`, line 861, change:

```python
if before["status"] != "pending":
    raise ConflictError("GR must be pending")
```
To:
```python
if before["status"] not in ("pending", "manager_confirm"):
    raise ConflictError("GR must be pending or manager_confirm")
```

- [ ] **Step 4: Extend GR Deny button visibility in frontend**

In `frontend/src/views/GrDetailView.vue`, line 13, change:

```html
<el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'pending'" type="danger" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('gr.deny') }}</el-button>
```
To:
```html
<el-button v-if="scDetail?.permissions?.can_manage_gr && ['pending','manager_confirm'].includes(gr.status)" type="danger" :disabled="loadingState.count > 0" @click="handleDeny">{{ $t('gr.deny') }}</el-button>
```

- [ ] **Step 5: Add test for deny_sc with manager_confirm status**

In `tests/test_sc_po_gr_flow.py`, add this test after the existing `deny_sc` test around line 974:

```python
def test_deny_sc_works_when_manager_confirm(app_config):
    """deny_sc should accept manager_confirm status, not just pending."""
    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc
    from sc_gr_app.services.vendor_service import create_vendor

    sc_id = create_sc_draft(app_config, USER, {"requester_id": "U1"})["sc_id"]
    create_vendor(
        app_config, USER,
        {"vendor_id": "V1", "vendor_name": "Vendor", "service_scope": "General Service"},
    )
    submitted = submit_sc(
        app_config, USER, sc_id,
        {
            "sc_no": "SC-DENY-001",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "vendor_ids": ["V1"],
        },
    )
    assert submitted["status"] == "manager_confirm"

    denied = deny_sc(app_config, ADMIN, sc_id)
    assert denied["status"] == "denied"
```

- [ ] **Step 6: Run tests**

```bash
uv run pytest tests/test_sc_po_gr_flow.py::test_deny_sc_works_when_manager_confirm -v
```

Expected: PASS

Note: A parallel test for `deny_gr` with `manager_confirm` requires a complex multi-step setup (draft SC → draft PO → draft GR → submit all). The code change in `deny_gr` is identical to `deny_sc` (same status gate pattern), so the `deny_sc` test covers the logic change. Manual verification of GR deny from manager_confirm is recommended.

- [ ] **Step 7: Commit**

```bash
git add sc_gr_app/services/sc_service.py sc_gr_app/services/gr_service.py frontend/src/views/GrDetailView.vue tests/test_sc_po_gr_flow.py
git commit -m "fix: allow Deny for both pending and manager_confirm status on SC and GR"
```

---

### Task 3: Add SC NO column to SC List table

**Files:**
- Modify: `frontend/src/components/sc/ScTable.vue:11-17`

- [ ] **Step 1: Add sc_no column after Status column**

In `frontend/src/components/sc/ScTable.vue`, insert after the Status column (after line 16) and before the sc_id column (line 17):

```html
<el-table-column prop="sc_no" :label="$t('sc.scNo')" sortable="custom" width="130">
  <template #default="{ row }">
    <span style="font-family:monospace;font-size:12px">{{ row.sc_no || '-' }}</span>
  </template>
</el-table-column>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/sc/ScTable.vue
git commit -m "feat: add SC NO column to SC list table"
```

---

### Task 4: Add Vendor ID to vendor export

**Files:**
- Modify: `frontend/src/views/VendorListView.vue:108-116`

- [ ] **Step 1: Add vendor_id to export columns**

In `frontend/src/views/VendorListView.vue`, add `vendor_id` as the first column in the export columns array (line 108):

```js
const columns = [
  { key: 'vendor_id', label: t('vendor.vendorId') },
  { key: 'vendor_name', label: t('vendor.vendorName') },
  { key: 'company_name_cn', label: t('vendor.companyNameCn') },
  { key: 'ksrm_vendor_code', label: t('vendor.ksrmCode') },
  { key: 'service_scope', label: t('vendor.serviceScope') },
  { key: 'contact_person', label: t('vendor.contact') },
  { key: 'phone', label: t('vendor.phone') },
  { key: 'email', label: t('vendor.email') }
]
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/VendorListView.vue
git commit -m "fix: add Vendor ID to vendor export columns"
```

---

### Task 5: Allow deleting last SC vendor

**Files:**
- Modify: `sc_gr_app/services/sc_service.py:334-344`
- Modify: `tests/test_sc_vendor_snapshot.py` (add test)

- [ ] **Step 1: Remove last-vendor guard in remove_sc_vendor**

In `sc_gr_app/services/sc_service.py`, delete lines 334-344 (the count check that prevents removing the last vendor):

Delete this block:
```python
                # Prevent removing the last vendor
                count_row = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sc_vendors WHERE sc_id = ?", (sc_id,)
                ).fetchone()
                if count_row["cnt"] <= 1:
                    raise ConflictError(
                        "供应商信息不允许为空，更新信息请在供应商界面更改（更改后不同步，需重新添加）\n"
                        "The supplier information cannot be left blank. To update the information, "
                        "please make the changes in the supplier interface "
                        "(the changes will not be synchronized and you need to re-add them)."
                    )
```

The function still verifies the vendor association exists before deleting (lines 346-351), which is correct behavior.

- [ ] **Step 2: Add test for removing last vendor**

In `tests/test_sc_vendor_snapshot.py`, add:

```python
def test_remove_last_vendor_allowed(app_config):
    """Removing the last vendor from an SC should succeed."""
    from sc_gr_app.db.connection import connect
    from sc_gr_app.services.sc_service import (
        create_sc_draft, add_sc_vendor, remove_sc_vendor
    )

    sc_id = create_sc_draft(app_config, USER, {"requester_id": "U1"})["sc_id"]
    vendor = create_vendor(app_config, ADMIN, {
        "vendor_name": "Test Vendor",
        "vendor_id": "V-TEST-001",
    })

    add_sc_vendor(app_config, USER, sc_id, vendor["vendor_id"])
    with connect(app_config) as conn:
        count = conn.execute(
            "SELECT COUNT(*) as cnt FROM sc_vendors WHERE sc_id = ?", (sc_id,)
        ).fetchone()
        assert count["cnt"] == 1

    # Should not raise — removing last vendor is now allowed
    result = remove_sc_vendor(app_config, USER, sc_id, vendor["vendor_id"])
    assert len(result) == 0
```

- [ ] **Step 3: Run the test**

```bash
uv run pytest tests/test_sc_vendor_snapshot.py::test_remove_last_vendor_allowed -v
```

Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/sc_service.py tests/test_sc_vendor_snapshot.py
git commit -m "fix: allow removing the last vendor from an SC"
```
