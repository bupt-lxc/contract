# Design: PO Vendor Restriction + User Seed Fix

Date: 2026-06-16

## Summary

Two independent changes:

1. Restrict PO vendor dropdown to only vendors linked to the parent SC (via `sc_vendors` junction table), not all vendors in the global catalog. Backend validation to match.
2. Fix `seed_users()` to not overwrite existing users when the database already has users (e.g., after a build update).

---

## 1. PO Vendor Restriction

### Current behavior

- `PoFormDialog.vue` accepts a `vendors` prop — an array of vendor objects for the dropdown
- All 3 views that use `PoFormDialog` pass ALL vendors from `useVendor()`:
  - **ScDetailView.vue line 119:** `:vendors="vendors"` where `vendors = computed(() => vendorState.rows)`
  - **PoListView.vue line 68:** `:vendors="vendors"` where `vendors = computed(() => vendorState.rows)`
  - **PoDetailView.vue line 112:** `:vendors="vendors"` where `vendors = computed(() => vendorState.rows)`
- Backend `create_po()` in [po_service.py:147-152](sc_gr_app/services/po_service.py#L147-L152) only validates vendor EXISTS in `vendors` table, not that it's linked to the SC
- `update_po()` (line 322 area) has the same gap

### SC-linked vendors data

- `sc_vendors` junction table already exists with SC-to-vendor links
- `get_sc_detail()` in [sc_service.py:1169](sc_gr_app/services/sc_service.py#L1169) already returns `vendors` field with SC-linked vendors via `_fetch_sc_vendors()`
- `_fetch_sc_vendors()` returns full vendor objects (from live `vendors` table or snapshot), sorted by name

### Changes

#### Frontend — ScDetailView.vue

**File:** `frontend/src/views/ScDetailView.vue`

Line 119: Change `:vendors="vendors"` to `:vendors="scVendors"`.

Add computed:
```js
const scVendors = computed(() => detail.value?.vendors || [])
```

Remove the now-unused `useVendor` import and `vendorState` usage (if no longer needed — check if `ScFormDialog` at line 111 also uses `vendors`).

Wait — `ScFormDialog` at line 111 also passes `:vendors="vendors"`. That's for the SC edit form's vendor section, which should still show all vendors for adding new SC vendors. So `vendorState` is still needed for `ScFormDialog`. Only `PoFormDialog` should get SC-linked vendors.

#### Frontend — PoDetailView.vue

**File:** `frontend/src/views/PoDetailView.vue`

Line 112 (in `<PoFormDialog>`): Change `:vendors="vendors"` to `:vendors="scVendors"`.

`scDetail` is already available — `scDetail.value?.vendors` has the SC-linked vendors.

Add computed:
```js
const scVendors = computed(() => scDetail.value?.vendors || [])
```

Remove `useVendor` import if `vendorState` is now unused — check: `vendorState` is not used elsewhere in the script. The `vendors` computed was only used for `PoFormDialog`. So we can remove `useVendor` import and the `vendors` computed.

#### Frontend — PoListView.vue

**File:** `frontend/src/views/PoListView.vue`

This is the tricky one. When creating a PO from the PO list view, the user first selects an SC from a dialog (`scSelectVisible`). The `selectedScRecord` comes from `search_scs` API which returns SC list items — NOT the full detail with vendors.

**Approach:** After SC selection, fetch the SC detail to get its linked vendors.

Line 68: Change `:vendors="vendors"` to `:vendors="scLinkedVendors"`.

Add:
```js
const scLinkedVendors = ref([])

async function confirmScSelection() {
  if (!selectedScId.value) return
  selectedScRecord.value = eligibleScs.value.find(s => s.sc_id === selectedScId.value) || null
  // Fetch SC-linked vendors
  try {
    const detail = await callApi('get_sc_detail', { sc_id: selectedScId.value })
    scLinkedVendors.value = detail?.vendors || []
  } catch { scLinkedVendors.value = [] }
  scSelectVisible.value = false
  poDialogMode.value = 'create'
  poDialogRecord.value = null
  poDialogVisible.value = true
}
```

Keep `useVendor` for the PO list's global vendor search/filter. The `vendors` computed is only used for `PoFormDialog` — replace it.

#### Backend — po_service.py

**File:** `sc_gr_app/services/po_service.py`

In `create_po()`, after the existing vendor-exists check (line 147-152), add an SC-vendor link check:

```python
# After: vendor = conn.execute("select vendor_id from vendors where vendor_id = ?", ...)
sc_vendor = conn.execute(
    "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
    (sc_id, data["vendor_id"]),
).fetchone()
if sc_vendor is None:
    raise ValidationError(
        f"Vendor {data['vendor_id']} is not linked to SC {sc_id}"
    )
```

In `update_po()` (around line 322), add the same check when `vendor_id` changes:

```python
if "vendor_id" in data and data["vendor_id"] != before["vendor_id"]:
    sc_vendor = conn.execute(
        "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
        (sc_id, data["vendor_id"]),
    ).fetchone()
    if sc_vendor is None:
        raise ValidationError(
            f"Vendor {data['vendor_id']} is not linked to SC {sc_id}"
        )
```

---

## 2. User Seed Fix

### Current behavior

`seed_users()` in [user_service.py:23-41](sc_gr_app/services/user_service.py#L23-L41) iterates over `SEED_USERS` and inserts any user whose `machine_id` doesn't exist yet:

```python
for machine_id, user_name, role, email in SEED_USERS:
    existing = conn.execute(
        "select user_id from users where machine_id = ?", (machine_id,),
    ).fetchone()
    if existing:
        continue
    # insert...
```

**Problem:** After a build update, if a user was manually promoted to admin, but their `machine_id` happens to be one of the SEED_USERS entries, they won't be reset (existing check prevents it). BUT: if a user was manually promoted and their `machine_id` is NOT in SEED_USERS, they're fine too. The actual issue is more subtle — the user reported "部分用户被重置了权限" (some users got their permissions reset).

Looking more carefully: the existing check only prevents re-insertion. It does NOT update existing users. So the seed function should NOT overwrite existing users' roles.

Wait — the current code already checks `if existing: continue`. So it should NOT overwrite. But the user reports permissions were reset. Let me think again...

The issue might be that the users table gets cleared during migration or something else. But the user specifically asked to change the logic: "如果已有数据集迁移，则使用已有的。当没有现有数据集时，再使用默认用户" — only seed when the database has no users at all.

### Change

**File:** `sc_gr_app/services/user_service.py`

Change `seed_users()` to check if ANY users exist first. If any users exist, skip the entire seeding:

```python
def seed_users(config: AppConfig) -> None:
    timestamp = now()
    with connect(config) as conn:
        existing = conn.execute(
            "select count(*) as cnt from users"
        ).fetchone()
        if existing and existing["cnt"] > 0:
            return  # Database already has users, skip seeding
        for machine_id, user_name, role, email in SEED_USERS:
            conn.execute(
                """
                insert into users (
                  user_id, machine_id, user_name, role, email, status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (f"U-{machine_id}", machine_id, user_name, role, email, timestamp, timestamp),
            )
        conn.commit()
```

This is simpler and matches the user's intent: seed only on a fresh/empty database. Once users exist (even one), never touch them.

---

## Files Changed (4 files)

| File | Changes |
|------|---------|
| `frontend/src/views/ScDetailView.vue` | Pass `detail.vendors` (SC-linked) instead of all vendors to PoFormDialog |
| `frontend/src/views/PoListView.vue` | Fetch SC detail on SC selection to get linked vendors; pass to PoFormDialog |
| `frontend/src/views/PoDetailView.vue` | Pass `scDetail.vendors` (SC-linked) instead of all vendors to PoFormDialog |
| `sc_gr_app/services/po_service.py` | Validate SC-vendor link in `create_po()` and `update_po()` |
| `sc_gr_app/services/user_service.py` | Change `seed_users()` to skip entirely if users table has any rows |
