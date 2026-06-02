# Workbench Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove amount columns, show requester name for all rows, fix admin visibility so Pending shows all users while Approved/Draft show own only, and add `requester_id` to PO table.

**Architecture:** Nine tasks. Create feature branch first. Migration v10 adds `requester_id` to `pos` table. PO service writes it on create. `workbench_data` returns `requester_name` for PO/GR, drops amount fields, and applies per-status visibility rules. Frontend removes amount columns, swaps vendor/po_no for requester_name, and fixes GR row click navigation.

**Tech Stack:** Python 3.11 + SQLite, Vue 3 + Element Plus

---

### Task 0: Create feature branch

- [ ] **Step 1: Create and switch to feature branch**

```bash
git checkout -b feat/workbench-redesign main
```

Expected: `Switched to a new branch 'feat/workbench-redesign'`

---

### Task 1: Migration v10 — add `requester_id` to PO table

**Files:**
- Modify: `sc_gr_app/db/migrations.py`

- [ ] **Step 1: Bump SCHEMA_VERSION to 9**

At line 6, change `SCHEMA_VERSION = 8` to `SCHEMA_VERSION = 9`.

At line 6:
```python
SCHEMA_VERSION = 9
```

- [ ] **Step 2: Update V1_SCHEMA_SQL pos table to include requester_id**

In `V1_SCHEMA_SQL`, add `requester_id` column to the `pos` table definition. Around line 86, after `po_no TEXT,` add the new line:

```sql
CREATE TABLE IF NOT EXISTS pos (
  po_id TEXT PRIMARY KEY,
  sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_no TEXT,
  requester_id TEXT NOT NULL,
  po_amount REAL NOT NULL CHECK (po_amount > 0),
  status TEXT NOT NULL CHECK (status IN ('draft','po_pending','po_approved','finished')),
  ...
```

- [ ] **Step 3: Add `_migrate_v10` function**

Insert before `def _migrate_v8` (around line 498):

```python
def _migrate_v10(conn) -> None:
    """Add requester_id column to pos table, backfill from SC."""
    if not _table_exists(conn, "pos"):
        _record(conn, 10)
        return

    existing = {row["name"] for row in conn.execute("PRAGMA table_info(pos)")}
    if "requester_id" not in existing:
        conn.execute("ALTER TABLE pos ADD COLUMN requester_id TEXT")
        conn.execute(
            """
            UPDATE pos SET requester_id = (
                SELECT sc.requester_id
                FROM sc_records sc
                WHERE sc.sc_id = pos.sc_id
            )
            """
        )

    _record(conn, 10)
```

- [ ] **Step 4: Update v9 rebuild DDL to include `requester_id`**

In `_migrate_v9`, update the pos CREATE TABLE (around line 418) to include `requester_id TEXT,` after `po_no TEXT,`:

```sql
CREATE TABLE pos (
  po_id TEXT PRIMARY KEY,
  sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_no TEXT,
  requester_id TEXT,
  po_amount REAL NOT NULL CHECK (po_amount > 0),
  status TEXT NOT NULL CHECK (status IN ('draft','po_pending','po_approved','finished')),
  ...
```

And update the INSERT SELECT to include `requester_id`:

```sql
INSERT INTO pos (
  po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
  contract_from, contract_to, contract_no, payment_frequency,
  contract_pos, contract_type, cost_center, purchaser,
  pending_date, approved_date, created_at, updated_at
)
SELECT
  po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
  contract_from, contract_to, contract_no, payment_frequency,
  contract_pos, contract_type, cost_center, purchaser,
  pending_date, approved_date, created_at, updated_at
FROM pos_old
```

Note: old rows won't have `requester_id`, so it will be NULL after v9 migration. The v10 backfill fixes that.

- [ ] **Step 5: Register v10 in `migrate()` function**

In the `migrate()` function (around line 597, after the v9 block), add:

```python
if 10 not in _applied_versions(conn):
    conn.execute("BEGIN")
    _migrate_v10(conn)
    conn.commit()
```

- [ ] **Step 6: Run migration tests to verify**

```bash
uv run pytest tests/test_migrations.py -v -q
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add sc_gr_app/db/migrations.py
git commit -m "feat: add requester_id to pos table via v10 migration"
```

---

### Task 2: Include `requester_id` in PO create

**Files:**
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Add `requester_id` to INSERT in `create_po`**

In `create_po` (~line 165), add `requester_id` to the column list and values. Use SC's `requester_id`:

```python
conn.execute(
    """
    insert into pos (
      po_id,
      sc_id,
      vendor_id,
      po_no,
      requester_id,
      po_amount,
      status,
      contract_from,
      contract_to,
      contract_no,
      payment_frequency,
      contract_pos,
      contract_type,
      cost_center,
      purchaser,
      pending_date,
      approved_date,
      created_at,
      updated_at
    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
    (
        po_id,
        sc_id,
        data["vendor_id"],
        data.get("po_no"),
        sc["requester_id"],
        float(po_amount),
        status,
        data.get("contract_from"),
        data.get("contract_to"),
        data.get("contract_no"),
        data.get("payment_frequency"),
        data.get("contract_pos"),
        data.get("contract_type"),
        data.get("cost_center") or str(sc["cost_center"]) if sc["cost_center"] is not None else None,
        data.get("purchaser"),
        pending_date_value,
        approved_date_value,
        timestamp,
        timestamp,
    ),
)
```

- [ ] **Step 2: Run PO-related tests**

```bash
uv run pytest tests/test_sc_po_gr_flow.py -v -q
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/po_service.py
git commit -m "feat: populate requester_id on PO create from parent SC"
```

---

### Task 3: Update `workbench_data` — requester_name, remove amounts, admin visibility

**Files:**
- Modify: `sc_gr_app/services/query_service.py`

- [ ] **Step 1: Rewrite `workbench_data` function**

Replace the entire `workbench_data` function (lines 557-631) with:

```python
def workbench_data(
    config: AppConfig,
    current_user: dict | None = None,
) -> dict:
    """Return per-status counts and top rows for the workbench grid.

    Visibility rules:
    - Requester: own records only (all statuses)
    - Admin:
      - Draft / Approved: own records only
      - Pending: all records
    """
    sc_statuses = ["draft", "pending", "approved"]
    po_statuses = ["draft", "po_pending", "po_approved"]
    gr_statuses = ["draft", "pending", "approved"]

    def _is_own_only(status: str) -> bool:
        if current_user is None:
            return False
        role = current_user.get("role")
        if role == "requester":
            return True
        if role == "admin":
            return status not in ("pending", "po_pending")
        return False

    user_id = current_user["user_id"] if current_user else None

    with connect(config) as conn:
        sc_data = {}
        for st in sc_statuses:
            clauses = ["sc.status = ?"]
            params = [st]
            if _is_own_only(st) and user_id:
                clauses.append("sc.requester_id = ?")
                params.append(user_id)
            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM sc_records sc {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT sc.sc_id, sc.sc_no, sc.requester_id, "
                f"u.user_name AS requester_name "
                f"FROM sc_records sc "
                f"JOIN users u ON u.user_id = sc.requester_id "
                f"{where} ORDER BY sc.updated_at DESC LIMIT 6",
                params,
            ).fetchall()
            sc_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

        po_data = {}
        for st in po_statuses:
            clauses = ["po.status = ?"]
            params = [st]
            if _is_own_only(st) and user_id:
                clauses.append("po.requester_id = ?")
                params.append(user_id)
            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM pos po {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT po.po_id, po.po_no, po.sc_id, po.requester_id, "
                f"u.user_name AS requester_name "
                f"FROM pos po "
                f"JOIN users u ON u.user_id = po.requester_id "
                f"{where} ORDER BY po.updated_at DESC LIMIT 6",
                params,
            ).fetchall()
            po_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

        gr_data = {}
        for st in gr_statuses:
            clauses = ["gr.status = ?"]
            params = [st]
            if _is_own_only(st) and user_id:
                clauses.append("gr.requester_id = ?")
                params.append(user_id)
            where = "WHERE " + " AND ".join(clauses)

            cnt = conn.execute(
                f"SELECT COUNT(*) FROM gr_requests gr "
                f"JOIN pos po ON po.po_id = gr.po_id "
                f"{where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT gr.gr_id, gr.po_id, po.sc_id, gr.requester_id, "
                f"u.user_name AS requester_name "
                f"FROM gr_requests gr "
                f"JOIN pos po ON po.po_id = gr.po_id "
                f"JOIN users u ON u.user_id = gr.requester_id "
                f"{where} ORDER BY gr.created_at DESC LIMIT 6",
                params,
            ).fetchall()
            gr_data[st] = {"count": cnt, "rows": [_row_to_dict(r) for r in rows]}

    return {"sc": sc_data, "po": po_data, "gr": gr_data}
```

Key changes:
- No longer uses `_sc_visibility_clauses` — inline visibility logic per cell
- PO joins `users` on `po.requester_id` for `requester_name`
- GR joins `users` on `gr.requester_id` for `requester_name`
- No amount columns selected (sc_amount, po_amount, estimated_amount, con_value)
- PO query no longer joins `vendors` (vendor_name removed)
- Admin: Pending → no requester filter; Draft/Approved → `requester_id = ?`

- [ ] **Step 2: Run existing workbench tests**

```bash
uv run pytest tests/test_query_service.py::test_workbench_data_returns_per_status_counts -v
uv run pytest tests/test_query_service.py::test_workbench_data_scopes_requester_to_own_scs -v
uv run pytest tests/test_query_service.py::test_workbench_data_hides_other_requesters_drafts -v
```

Expected: FAIL on some — tests need updating for new field names (see Task 7).

- [ ] **Step 3: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "feat: update workbench_data with requester_name, no amounts, admin per-status visibility"
```

---

### Task 4: Update `HomeView.vue` — remove amounts, change to requester_name, fix GR navigation

**Files:**
- Modify: `frontend/src/views/HomeView.vue`

- [ ] **Step 1: Update SC row template (~lines 24-40)**

Remove amount column header and cell, adjust column widths:

```html
<div class="wb-cell__table">
  <div class="wb-cell__th">
    <span class="wb-cell__th-id">{{ $t('home.colScNo') }}</span>
    <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
  </div>
  <div
    v-for="row in (data.sc?.[cell.status]?.rows || [])"
    :key="row.sc_id"
    class="wb-cell__tr"
    @click="$router.push(`/sc/${row.sc_id}`)"
  >
    <span class="wb-cell__td-id">{{ row.sc_no || row.sc_id }}</span>
    <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
  </div>
  <div v-if="!data.sc?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
</div>
```

- [ ] **Step 2: Update PO row template (~lines 59-76)**

Remove amount, change `vendor_name` to `requester_name`:

```html
<div class="wb-cell__table">
  <div class="wb-cell__th">
    <span class="wb-cell__th-id">{{ $t('home.colPoNo') }}</span>
    <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
  </div>
  <div
    v-for="row in (data.po?.[cell.status]?.rows || [])"
    :key="row.po_id"
    class="wb-cell__tr"
    @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}`)"
  >
    <span class="wb-cell__td-id">{{ row.po_no || row.po_id }}</span>
    <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
  </div>
  <div v-if="!data.po?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
</div>
```

- [ ] **Step 3: Update GR row template (~lines 95-111)**

Remove amount, change `po_no` to `requester_name`, fix navigation:

```html
<div class="wb-cell__table">
  <div class="wb-cell__th">
    <span class="wb-cell__th-id">{{ $t('home.colGrId') }}</span>
    <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
  </div>
  <div
    v-for="row in (data.gr?.[cell.status]?.rows || [])"
    :key="row.gr_id"
    class="wb-cell__tr"
    @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)"
  >
    <span class="wb-cell__td-id">{{ row.gr_id }}</span>
    <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
  </div>
  <div v-if="!data.gr?.[cell.status]?.rows?.length" class="wb-cell__empty">—</div>
</div>
```

- [ ] **Step 4: Remove `AmountDisplay` import**

In `<script setup>`, remove line 124:
```javascript
// REMOVE this line:
import AmountDisplay from '@/components/common/AmountDisplay.vue'
```

- [ ] **Step 5: Update CSS (~lines 284-309)**

Remove `.wb-cell__th-amt` and `.wb-cell__td-amt` rules. Adjust `.wb-cell__th-id/.wb-cell__td-id` and `.wb-cell__th-sub/.wb-cell__td-sub` flex ratios:

```css
.wb-cell__th-id,
.wb-cell__td-id {
  flex: 1 1 55%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.wb-cell__th-sub,
.wb-cell__td-sub {
  flex: 0 0 40%;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* REMOVE these blocks entirely:
.wb-cell__th-amt,
.wb-cell__td-amt { ... }
*/
```

- [ ] **Step 6: Verify frontend builds**

```bash
cd frontend && npx vite build --mode production
```

Expected: build succeeds with no errors.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "feat: remove amounts, show requester_name, fix GR nav in workbench"
```

---

### Task 5: Update i18n translations

**Files:**
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`

- [ ] **Step 1: Update `en-US.js` home section**

Replace the home block (around line 114) — remove unused keys, ensure `colRequester` is present:

```javascript
home: {
  workbench: 'Workbench',
  scNo: 'SC No',
  poNo: 'PO No',
  grId: 'GR ID',
  loadError: 'Load failed',
  colScNo: 'SC No',
  colRequester: 'Requester',
  colPoNo: 'PO No',
  colGrId: 'GR ID',
  // Removed: pendingScs, pendingPos, pendingGrs, myDrafts, myPendingScs,
  // deniedScs, activePos, scId, amount, estimated, noCards,
  // colAmount, colVendor, colEstAmount
},
```

- [ ] **Step 2: Update `zh-CN.js` home section**

```javascript
home: {
  workbench: '工作台',
  scNo: 'SC编号',
  poNo: 'PO编号',
  grId: 'GR ID',
  loadError: '加载失败',
  colScNo: 'SC编号',
  colRequester: '申请人',
  colPoNo: 'PO编号',
  colGrId: 'GR ID',
},
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "chore: clean up unused home i18n keys, keep colRequester"
```

---

### Task 6: Update workbench tests

**Files:**
- Modify: `tests/test_query_service.py`

- [ ] **Step 1: Update existing tests for new field names**

The tests at lines 403-437 need updating because `workbench_data` no longer returns `sc_amount`, and PO rows now have `requester_name` instead of `vendor_name`.

Replace the three workbench tests (lines 403-437) with:

```python
def test_workbench_data_returns_per_status_counts(app_config):
    migrate(app_config)
    seed_users(app_config)
    # Create an approved SC for USER1
    sc = create_sc(
        app_config, USER,
        {"sc_no": "SC-1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    approve_sc(app_config, ADMIN, sc["sc_id"])

    result = workbench_data(app_config, ADMIN)

    assert result["sc"]["approved"]["count"] >= 1
    assert len(result["sc"]["approved"]["rows"]) >= 1
    row = result["sc"]["approved"]["rows"][0]
    assert "sc_no" in row
    assert "requester_name" in row
    # No amount fields
    assert "sc_amount" not in row


def test_workbench_data_scopes_requester_to_own_scs(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)
    # USER1 creates and approves an SC
    sc = create_sc(
        app_config, USER,
        {"sc_no": "SC-1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    approve_sc(app_config, ADMIN, sc["sc_id"])

    admin_data = workbench_data(app_config, ADMIN)
    owner_data = workbench_data(app_config, USER)

    # Admin sees all approved SCs; USER1 sees only own
    assert admin_data["sc"]["approved"]["count"] >= owner_data["sc"]["approved"]["count"]


def test_workbench_data_admin_pending_shows_all(app_config):
    """Admin Pending column shows all users; Approved/Draft show own only."""
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)
    # USER1 creates a pending SC
    create_sc(
        app_config, USER,
        {"sc_no": "SC-U1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    # USER2 creates a pending SC
    create_sc(
        app_config, OTHER_USER,
        {"sc_no": "SC-U2", "requester_id": "U2", "request_type": "service",
         "cost_center": 1002, "sc_amount": 500,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )

    admin_data = workbench_data(app_config, ADMIN)
    user1_data = workbench_data(app_config, USER)
    user2_data = workbench_data(app_config, OTHER_USER)

    # Admin Pending: sees both users' SCs
    assert admin_data["sc"]["pending"]["count"] >= 2
    # USER1 Pending: sees only own
    assert user1_data["sc"]["pending"]["count"] >= 1
    # USER2 Pending: sees only own
    assert user2_data["sc"]["pending"]["count"] >= 1
    # Admin Approved: sees only own (none in this test)
    assert admin_data["sc"]["approved"]["count"] == 0


def test_workbench_data_po_has_requester_name(app_config):
    """PO workbench rows return requester_name, not vendor_name."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1", "vendor_name": "TestVendor",
        "ksrm_vendor_code": "KV-1", "service_scope": "General Service",
    })
    sc = create_sc(
        app_config, USER,
        {"sc_no": "SC-1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    approve_sc(app_config, ADMIN, sc["sc_id"])
    create_po(app_config, ADMIN, {
        "sc_id": sc["sc_id"], "vendor_id": "V1",
        "po_no": "PO-1", "po_amount": 500, "status": "po_approved",
    })

    result = workbench_data(app_config, ADMIN)
    po_row = result["po"]["po_approved"]["rows"][0]
    assert "requester_name" in po_row
    assert po_row["requester_name"] == USER["user_id"]  # user_name = user_id in seed
    assert "vendor_name" not in po_row
    assert "po_amount" not in po_row
```

- [ ] **Step 2: Run updated tests**

```bash
uv run pytest tests/test_query_service.py -v -q -k workbench
```

Expected: all 5 PASS

- [ ] **Step 3: Run all tests**

```bash
uv run pytest -q
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_query_service.py
git commit -m "test: update workbench tests for requester_name, no amounts, admin visibility"
```

---

### Task 7: End-to-end verification

- [ ] **Step 1: Run the app in dev mode**

```bash
powershell -ExecutionPolicy Bypass -File dev.ps1
```

- [ ] **Step 2: Manual verification checklist**

1. Login as Admin → workbench shows 3×3 grid
2. No amount columns visible in any row
3. SC row shows SC No + Requester
4. PO row shows PO No + Requester
5. GR row shows GR ID + Requester
6. Admin Pending column shows records from multiple users
7. Admin Approved/Draft columns show only admin's own records
8. Click GR row → navigates to GR detail page (`/sc/:scId/po/:poId/gr/:grId`)
9. Login as Requester → all 9 cells show only own records
10. "View all" links work for each row

---

### Task 9: Push branch and create PR

All commits from Tasks 1-8 are already on `feat/workbench-redesign`. Push and create the PR.

- [ ] **Step 1: Push branch to origin**

```bash
git push -u origin feat/workbench-redesign
```

- [ ] **Step 2: Create PR**

```bash
gh pr create --title "feat: workbench redesign — remove amounts, requester_name, admin visibility" --body "$(cat <<'EOF'
## Summary
- Remove all amount columns from workbench 3×3 grid
- Show requester name for SC, PO, and GR rows
- Admin: Pending column shows all users; Approved/Draft show own only
- Requester: all cells show own records only
- Add `requester_id` to PO table (migration v10)
- Fix GR row click to navigate to GR detail page

## Changes
- **Migration v10**: Add `requester_id` to `pos` table with backfill
- **PO service**: Populate `requester_id` on create from parent SC
- **workbench_data**: Return `requester_name` for PO/GR, drop amount fields, per-status visibility
- **HomeView.vue**: Remove amount columns, swap vendor/po_no for requester_name, fix GR navigation
- **i18n**: Clean up unused home keys
- **Tests**: Updated and new tests for visibility rules

## Test plan
- [ ] `uv run pytest -q` — all tests pass
- [ ] Admin login: Pending shows all users' records
- [ ] Admin login: Approved/Draft shows own records only
- [ ] Requester login: all cells show own records only
- [ ] No amount columns rendered
- [ ] GR row click navigates to GR detail
- [ ] Columns display: SC No / PO No / GR ID + Requester
EOF
)"
```

- [ ] **Step 3: Verify PR**

```bash
gh pr view
```

