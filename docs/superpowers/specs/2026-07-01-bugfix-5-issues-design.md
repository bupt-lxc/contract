# Bugfix: 5 UI & Logic Issues

**Date:** 2026-07-01
**Status:** approved

## Issues & Fixes

### 1. GR Detail missing Submit button

**File:** `frontend/src/views/GrDetailView.vue`

Draft GRs have no Submit button in the detail view header. The `submitGr()` function already exists in the `useGr` composable and the backend `submit_gr` endpoint works.

**Fix:** Add a Submit button for draft GRs (visible when `can_manage_gr`):

```html
<el-button v-if="scDetail?.permissions?.can_manage_gr && gr.status === 'draft'" type="primary" @click="handleSubmit">{{ $t('common.submit') }}</el-button>
```

Add `handleSubmit` calling `submitGr(grId)`, then refresh detail.

---

### 2. SC and GR `manager_confirm` status cannot be Denied

Currently both SC and GR only allow Deny when status is `pending`. The `manager_confirm` status should also be deny-able.

**Fix — SC backend** (`sc_gr_app/services/sc_service.py`):
- `_sc_permissions()` line 170: change `can_deny_sc` from `is_admin and is_pending` to `is_admin and (is_pending or is_manager_confirm)`
- `deny_sc()` line 848: change status gate from `"pending"` to `("pending", "manager_confirm")`

**Fix — GR backend** (`sc_gr_app/services/gr_service.py`):
- `deny_gr()` line 861: change status gate from `"pending"` to `("pending", "manager_confirm")`

**Fix — GR frontend** (`frontend/src/views/GrDetailView.vue`):
- Line 13: change Deny button visibility from `gr.status === 'pending'` to `['pending','manager_confirm'].includes(gr.status)`

SC Deny button already uses `permissions.can_deny_sc` — no frontend change needed.

---

### 3. SC List missing SC NO column

**File:** `frontend/src/components/sc/ScTable.vue`

The SC table shows `sc_id` (UUID) but not the human-readable `sc_no` (e.g., "SC-2026-001").

**Fix:** Add `sc_no` as the second column (after Status, before sc_id), width ~120px, sortable.

---

### 4. Vendor export missing Vendor ID

**File:** `frontend/src/views/VendorListView.vue`

The export columns array (lines 108-116) does not include `vendor_id`.

**Fix:** Add `{ key: 'vendor_id', label: t('vendor.vendorId') }` to the export columns.

---

### 5. Cannot delete last SC vendor

**File:** `sc_gr_app/services/sc_service.py`

`remove_sc_vendor()` blocks removal when only 1 vendor remains (lines 334-344), with error "supplier information cannot be blank." Empty vendor lists are valid.

**Fix:** Remove the count check guard. The function will still verify the vendor association exists before deleting, but will no longer block removal of the last vendor.
