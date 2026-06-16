# PO Vendor Restriction + User Seed Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict PO vendor dropdown to SC-linked vendors + fix seed_users to not touch existing databases.

**Architecture:** Frontend passes SC-linked vendors instead of all vendors to PoFormDialog. Backend adds sc_vendors check in create_po/update_po. seed_users checks for any existing users before seeding.

**Tech Stack:** Vue 3 + Element Plus (frontend), Python 3.11 + SQLite (backend)

---

### Task 1: Backend — Validate SC-vendor link in create_po and update_po

**Files:**
- Modify: `sc_gr_app/services/po_service.py:147-152` (create_po)
- Modify: `sc_gr_app/services/po_service.py:369-375` (update_po)
- Test: `tests/test_po_service.py`

- [ ] **Step 1: Add SC-vendor link validation in create_po**

After the existing vendor-exists check in `create_po()` (line 152 `raise NotFound(...)`), add:

```python
                sc_vendor = conn.execute(
                    "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                    (sc_id, data["vendor_id"]),
                ).fetchone()
                if sc_vendor is None:
                    raise ValidationError(
                        f"Vendor {data['vendor_id']} is not linked to SC {sc_id}"
                    )
```

- [ ] **Step 2: Add SC-vendor link validation in update_po**

In `update_po()`, after the existing vendor-exists check (line 375 `raise NotFound(...)`), add:

```python
                    sc_vendor = conn.execute(
                        "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                        (sc_id, merged["vendor_id"]),
                    ).fetchone()
                    if sc_vendor is None:
                        raise ValidationError(
                            f"Vendor {merged['vendor_id']} is not linked to SC {sc_id}"
                        )
```

- [ ] **Step 3: Write tests**

In `tests/test_po_service.py`, add a test class `TestPoVendorRestriction`:

```python
class TestPoVendorRestriction:
    def test_create_po_rejects_unlinked_vendor(self, app_config):
        """PO creation must fail when vendor is not linked to the SC."""
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users
        from sc_gr_app.services.sc_service import create_sc_draft, submit_sc
        from sc_gr_app.services.vendor_service import create_vendor
        from sc_gr_app.services.po_service import create_po
        from sc_gr_app.errors import ValidationError

        migrate(app_config)
        seed_users(app_config)

        # Create admin user
        with connect(app_config) as conn:
            admin = dict(conn.execute("select * from users where role = 'admin' limit 1").fetchone())

        # Create SC
        sc = create_sc_draft(app_config, admin, {"requester_id": admin["user_id"]})

        # Create vendor but do NOT link to SC
        vendor = create_vendor(app_config, admin, {
            "vendor_name": "Unlinked Vendor",
            "ksrm_vendor_code": "K999",
        })

        # Try to create PO with unlinked vendor
        with pytest.raises(ValidationError, match="not linked to SC"):
            create_po(app_config, admin, {
                "sc_id": sc["sc_id"],
                "vendor_id": vendor["vendor_id"],
                "po_amount": "1000",
            })

    def test_update_po_rejects_unlinked_vendor(self, app_config):
        """PO update must fail when changing to a vendor not linked to the SC."""
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users
        from sc_gr_app.services.sc_service import create_sc_draft, add_sc_vendor
        from sc_gr_app.services.vendor_service import create_vendor
        from sc_gr_app.services.po_service import create_po, update_po
        from sc_gr_app.errors import ValidationError

        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            admin = dict(conn.execute("select * from users where role = 'admin' limit 1").fetchone())

        sc = create_sc_draft(app_config, admin, {"requester_id": admin["user_id"]})

        # Create two vendors
        v1 = create_vendor(app_config, admin, {"vendor_name": "Vendor A", "ksrm_vendor_code": "KA"})
        v2 = create_vendor(app_config, admin, {"vendor_name": "Vendor B", "ksrm_vendor_code": "KB"})

        # Link only v1 to SC
        add_sc_vendor(app_config, admin, sc["sc_id"], v1["vendor_id"])

        # Create PO with linked vendor v1
        po = create_po(app_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v1["vendor_id"],
            "po_amount": "1000",
        })

        # Try to update PO to unlinked vendor v2
        with pytest.raises(ValidationError, match="not linked to SC"):
            update_po(app_config, admin, po["po_id"], {"vendor_id": v2["vendor_id"]})
```

- [ ] **Step 4: Run tests**

```bash
uv run pytest tests/test_po_service.py::TestPoVendorRestriction -v
```

Expected: 2 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/po_service.py tests/test_po_service.py
git commit -m "feat: validate SC-vendor link when creating/updating POs"
```

---

### Task 2: Frontend — ScDetailView pass SC-linked vendors to PoFormDialog

**Files:**
- Modify: `frontend/src/views/ScDetailView.vue:115-121`

- [ ] **Step 1: Add scVendors computed and change vendors prop**

In `<script setup>`, add after line 174:

```js
const scVendors = computed(() => detail.value?.vendors || [])
```

Change line 119 from `:vendors="vendors"` to `:vendors="scVendors"`.

The `vendors` computed (`vendorState.rows`) is still used by `ScFormDialog` at line 111, so keep `useVendor` import.

- [ ] **Step 2: Commit**

```bash
git add frontend/src/views/ScDetailView.vue
git commit -m "feat: restrict PO vendor dropdown to SC-linked vendors in ScDetailView"
```

---

### Task 3: Frontend — PoDetailView pass SC-linked vendors to PoFormDialog

**Files:**
- Modify: `frontend/src/views/PoDetailView.vue:109-115` (template)
- Modify: `frontend/src/views/PoDetailView.vue:171` (script)

- [ ] **Step 1: Add scVendors computed and change vendors prop**

In `<script setup>`, replace line 171:

```js
// Remove: const vendors = computed(() => vendorState.rows)
// Add:
const scVendors = computed(() => scDetail.value?.vendors || [])
```

Change line 112 from `:vendors="vendors"` to `:vendors="scVendors"`.

Remove `useVendor` import (line 137: `import { useVendor } from '@/composables/useVendor.js'`).

Remove `const { state: vendorState, searchVendors } = useVendor()` at line 157.

Check: Is `vendorState` or `searchVendors` used elsewhere in the file? Lines 157, 171. After removal, `searchVendors` is still called on mount? Let's check...

Line 356: `await Promise.all([fetchDetail(scId.value), searchVendors()])` — this needs to stay because `searchVendors` populates the vendor cache for other views. Actually no — `useVendor()` is a composable that maintains global state. If we remove it from this component, the vendor list won't be fetched for the vendor filter in the PO list view.

Wait, this is a detail view. The `searchVendors` call here prefetches vendors for the global vendor state. Other views also call `searchVendors`. If we remove it here, the first time someone visits PoDetailView, vendors won't be loaded, but they'll be loaded when navigating to other views.

Actually, since we're no longer using `useVendor` in this component at all, we should remove the import and the call. Other views that need vendors will load them independently.

- [ ] **Step 2: Remove searchVendors call from onMounted**

Line 356: Change from:
```js
await Promise.all([fetchDetail(scId.value), searchVendors()])
```
to:
```js
await fetchDetail(scId.value)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PoDetailView.vue
git commit -m "feat: restrict PO vendor dropdown to SC-linked vendors in PoDetailView"
```

---

### Task 4: Frontend — PoListView fetch SC-linked vendors on SC selection

**Files:**
- Modify: `frontend/src/views/PoListView.vue:64-71` (template)
- Modify: `frontend/src/views/PoListView.vue:93-97,167-180` (script)

- [ ] **Step 1: Add scLinkedVendors ref and update confirmScSelection**

Replace `const vendors = computed(() => vendorState.rows)` at line 97 with:

```js
const scLinkedVendors = ref([])
```

Change line 68 from `:vendors="vendors"` to `:vendors="scLinkedVendors"`.

Update `confirmScSelection()` (lines 173-180):

```js
async function confirmScSelection() {
  if (!selectedScId.value) return
  selectedScRecord.value = eligibleScs.value.find(s => s.sc_id === selectedScId.value) || null
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

Remove `useVendor` import (line 82) and `const { state: vendorState, searchVendors } = useVendor()` (line 93).

Check: Is `vendorState` or `searchVendors` used elsewhere? Line 93 only. Remove both.

Check: Is `searchVendors` called in `onMounted`? Let's check...

Lines 257-260 area:
```js
onMounted(async () => {
  await searchVendors()
  await searchPos()
})
```

If we remove `searchVendors`, the PO list view will still work because the PO search returns vendor names via JOIN. But the global vendor filter dropdown in the advanced filter bar won't have vendors loaded.

Actually, looking at the filter config (lines 129-144), there's a `vendor_id` and `vendor_name` filter — but those are text input filters, not select dropdowns. So no vendor dropdown needs populating.

Let's remove the `searchVendors` call and the `useVendor` import entirely.

- [ ] **Step 2: Remove searchVendors from onMounted**

```js
onMounted(async () => {
  await searchPos()
})
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/PoListView.vue
git commit -m "feat: fetch SC-linked vendors when creating PO from PoListView"
```

---

### Task 5: Fix seed_users to skip when users table has any rows

**Files:**
- Modify: `sc_gr_app/services/user_service.py:23-41`
- Test: `tests/test_user_service.py`

- [ ] **Step 1: Change seed_users logic**

Replace the body of `seed_users()`:

```python
def seed_users(config: AppConfig) -> None:
    timestamp = now()
    with connect(config) as conn:
        existing = conn.execute(
            "select count(*) as cnt from users"
        ).fetchone()
        if existing and existing["cnt"] > 0:
            return
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

- [ ] **Step 2: Write tests**

In `tests/test_user_service.py`, add:

```python
class TestSeedUsersSkipWhenNotEmpty:
    def test_seed_users_inserts_when_table_empty(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            count = conn.execute("select count(*) as cnt from users").fetchone()["cnt"]
        assert count == 6

    def test_seed_users_skips_when_users_exist(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)

        # Insert a custom user first
        with connect(app_config) as conn:
            conn.execute(
                "insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
                "values ('U-CUSTOM', 'CUSTOM01', 'Custom User', 'admin', 'custom@test.com', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            conn.commit()

        # Seed should skip entirely
        seed_users(app_config)

        with connect(app_config) as conn:
            users = conn.execute("select * from users").fetchall()
        # Only the custom user, no seed users added
        assert len(users) == 1
        assert users[0]["machine_id"] == "CUSTOM01"
        assert users[0]["role"] == "admin"

    def test_seed_users_preserves_existing_roles(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)

        # Simulate: existing DB with manually-changed roles
        with connect(app_config) as conn:
            conn.execute(
                "insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
                "values ('U-V2SE7PP', 'V2SE7PP', 'Li, Xingchen', 'requester', 'test@test.com', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            conn.commit()

        seed_users(app_config)

        with connect(app_config) as conn:
            user = conn.execute("select * from users where machine_id = 'V2SE7PP'").fetchone()
        # Role should stay as manually-set 'requester', not be reset to SEED_USERS 'admin'
        assert user["role"] == "requester"
```

- [ ] **Step 3: Run tests**

```bash
uv run pytest tests/test_user_service.py::TestSeedUsersSkipWhenNotEmpty -v
```

Expected: 3 tests pass.

- [ ] **Step 4: Run full test suite**

```bash
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/user_service.py tests/test_user_service.py
git commit -m "fix: skip seed_users when database already has users"
```
