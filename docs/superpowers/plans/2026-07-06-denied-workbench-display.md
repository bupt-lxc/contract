# Denied SC/GR WorkBench Display — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show denied SC and GR records in a conditional top section of the WorkBench.

**Architecture:** Add `"denied"` to the backend status lists and visibility rules, then render a new conditional denied section at the top of the HomeView template. The section uses the existing `wb-cell` BEM pattern with new `--denied` CSS modifiers. Clicking navigates to existing list views filtered by `?status=denied`.

**Tech Stack:** Python (SQLite queries), Vue 3 (Composition API), Element Plus, vue-i18n

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `sc_gr_app/services/query_service.py` | Modify | Add `"denied"` to SC/GR status lists, update `_is_own_only`, add `denied_by`/`denied_at` to GR SELECT |
| `frontend/src/i18n/locales/zh-CN.js` | Modify | Add `home.denied: '已驳回'` |
| `frontend/src/i18n/locales/en-US.js` | Modify | Add `home.denied: 'Denied'` |
| `frontend/src/views/HomeView.vue` | Modify | New denied section template, computed props, `headStatus` update, CSS rules |
| `tests/test_query_service.py` | Modify | 5 new tests for denied visibility rules |

---

### Task 1: Backend — Add denied to workbench_data

**Files:**
- Modify: `sc_gr_app/services/query_service.py:653-655,664,752-754`

- [ ] **Step 1: Add `"denied"` to sc_statuses and gr_statuses**

In `sc_gr_app/services/query_service.py`, change lines 653 and 655:

```python
sc_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
# ...
gr_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
```

- [ ] **Step 2: Add `"denied"` to `_is_own_only` exclusion set**

Change line 664 so admins see all denied records:

```python
return status not in ("pending", "active", "manager_confirm", "approved", "denied")
```

- [ ] **Step 3: Add `denied_by`, `denied_at` to GR SELECT**

In lines 752-754, add the two columns after `gr.submitted_date`:

```python
rows = conn.execute(
    f"SELECT gr.gr_id, gr.po_id, po.sc_id, gr.requester_id, "
    f"gr.created_at, gr.pending_date, gr.submitted_date, "
    f"gr.denied_by, gr.denied_at, "
    f"u.user_name AS requester_name "
    f"FROM gr_requests gr "
    f"JOIN pos po ON po.po_id = gr.po_id "
    f"JOIN users u ON u.user_id = gr.requester_id "
    f"{where} ORDER BY gr.created_at ASC LIMIT 6",
    params,
).fetchall()
```

- [ ] **Step 4: Run existing tests to verify no regressions**

```bash
cd c:/Users/V2SE7PP/Projects/contract && uv run pytest tests/test_query_service.py -v -k "workbench" 2>&1 | head -40
```

Expected: 4 existing workbench tests pass (they only test `approved` and `pending` statuses).

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/services/query_service.py
git commit -m "feat: add denied status to workbench_data for SC and GR"
```

> **Note on SC vs GR data asymmetry:** `sc_records` has no `denied_by`/`denied_at` columns, and `deny_sc` does not persist them. `gr_requests` has both columns and `deny_gr` populates them. This is a pre-existing condition — the SC cell template uses `deadline` for the date column (not `denied_at`), and the GR cell template uses `created_at`. No runtime issue.

---

### Task 2: i18n — Add `home.denied` translations

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.js:171`
- Modify: `frontend/src/i18n/locales/en-US.js`

- [ ] **Step 1: Add translation to zh-CN.js**

In `frontend/src/i18n/locales/zh-CN.js`, inside the `home` block (after line 170 `viewAllOfType`), add:

```javascript
    denied: '已驳回',
```

The `home` block should end with:

```javascript
    viewAllOfType: '查看此类全部',
    denied: '已驳回',
  },
```

- [ ] **Step 2: Read en-US.js to find exact insertion point**

Read `frontend/src/i18n/locales/en-US.js` around the `home` block end.

- [ ] **Step 3: Add translation to en-US.js**

Inside the `home` block in `frontend/src/i18n/locales/en-US.js`, add:

```javascript
    denied: 'Denied',
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.js frontend/src/i18n/locales/en-US.js
git commit -m "feat: add home.denied i18n key for denied WorkBench section"
```

---

### Task 3: Frontend — Denied section in HomeView

**Files:**
- Modify: `frontend/src/views/HomeView.vue`

- [ ] **Step 1: Add denied section template above first SC row**

Insert the new denied section block between `</div>` (line 7, `wb-error` end) and `<!-- SC Row 1 -->` (line 9). The denied section goes at the top of the WorkBench, above all existing rows:

```html
    <!-- Denied Section -->
    <div class="wb-row" v-if="deniedScCount > 0 || deniedGrCount > 0">
      <div class="wb-row__header">
        <span class="wb-row__label">{{ $t('home.denied') }}</span>
      </div>
      <div class="wb-grid wb-grid--2">
        <div
          v-if="deniedScCount > 0"
          class="wb-cell wb-cell--denied"
        >
          <div class="wb-cell__head wb-cell__head--denied">
            <span class="wb-cell__status">{{ $t('status.denied') }}</span>
            <span class="wb-cell__count">{{ deniedScCount }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th wb-cell__th--sc5">
              <span class="wb-cell__th-no">{{ $t('home.colScNo') }}</span>
              <span class="wb-cell__th-req">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-type">{{ $t('home.colType') }}</span>
              <span class="wb-cell__th-amt">{{ $t('home.colAmount') }}</span>
              <span class="wb-cell__th-date">{{ $t('home.colDeadline') }}</span>
            </div>
            <div
              v-for="row in (data.sc?.denied?.rows || [])"
              :key="row.sc_id"
              class="wb-cell__tr wb-cell__tr--sc5"
              @click="$router.push(`/sc/${row.sc_id}`)"
            >
              <span class="wb-cell__td-no" :title="row.sc_no">{{ row.sc_no || shortId(row.sc_id) }}</span>
              <span class="wb-cell__td-req">{{ row.requester_name }}</span>
              <span class="wb-cell__td-type">{{ typeLabel(row.request_type) }}</span>
              <span class="wb-cell__td-amt">{{ formatCurrency(row.sc_amount, row.currency) }}</span>
              <span class="wb-cell__td-date">{{ (row.deadline || '').slice(0, 10) || '-' }}</span>
            </div>
            <div v-if="!data.sc?.denied?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push('/sc?status=denied')">{{ $t('home.viewAllOfType') }}</div>
        </div>
        <div
          v-if="deniedGrCount > 0"
          class="wb-cell wb-cell--denied"
        >
          <div class="wb-cell__head wb-cell__head--denied">
            <span class="wb-cell__status">{{ $t('status.denied') }}</span>
            <span class="wb-cell__count">{{ deniedGrCount }}</span>
          </div>
          <div class="wb-cell__table">
            <div class="wb-cell__th">
              <span class="wb-cell__th-id">{{ $t('home.colGrId') }}</span>
              <span class="wb-cell__th-sub">{{ $t('home.colRequester') }}</span>
              <span class="wb-cell__th-date">{{ $t('home.colCreatedAt') }}</span>
            </div>
            <div
              v-for="row in (data.gr?.denied?.rows || [])"
              :key="row.gr_id"
              class="wb-cell__tr"
              @click="$router.push(`/sc/${row.sc_id}/po/${row.po_id}/gr/${row.gr_id}`)"
            >
              <span class="wb-cell__td-id" :title="row.gr_id">{{ shortId(row.gr_id) }}</span>
              <span class="wb-cell__td-sub">{{ row.requester_name }}</span>
              <span class="wb-cell__td-date">{{ (row.created_at || '').slice(0, 10) || '-' }}</span>
            </div>
            <div v-if="!data.gr?.denied?.rows?.length" class="wb-cell__empty">—</div>
          </div>
          <div class="wb-cell__link" @click="$router.push('/gr?status=denied')">{{ $t('home.viewAllOfType') }}</div>
        </div>
      </div>
    </div>
```

- [ ] **Step 2: Add computed properties in `<script setup>`**

Insert after existing computed properties (after `grCells`, around line 221):

```javascript
const deniedScCount = computed(() => data.value.sc?.denied?.count ?? 0)
const deniedGrCount = computed(() => data.value.gr?.denied?.count ?? 0)
```

- [ ] **Step 3: Add denied to `headStatus` function**

In the `headStatus` function, add before `return 'draft'`:

```javascript
  if (status.includes('denied')) return 'denied'
```

The complete function should read:

```javascript
function headStatus(status) {
  if (status.includes('draft')) return 'draft'
  if (status.includes('manager')) return 'manager'
  if (status.includes('active')) return 'pending'
  if (status.includes('pending')) return 'pending'
  if (status.includes('approved')) return 'approved'
  if (status.includes('finished')) return 'approved'
  if (status.includes('denied')) return 'denied'
  return 'draft'
}
```

- [ ] **Step 4: Add CSS rules**

Insert after the existing status color blocks (after line 384):

```css
.wb-cell__head--denied    { background: #fef2f2; }
.wb-cell--denied .wb-cell__table { background: #fefaf9; }
```

Also add the `wb-section` class (though renamed to reuse `wb-row` pattern, so no `wb-section` needed — the denied section uses `.wb-row` which already exists). The denied section uses existing `.wb-row`, `.wb-row__header`, `.wb-row__label`, `.wb-grid`, `.wb-grid--2` classes — only the `--denied` color modifiers are new.

- [ ] **Step 5: Build frontend to verify no compile errors**

```bash
cd c:/Users/V2SE7PP/Projects/contract/frontend && npm run build 2>&1 | tail -20
```

Expected: Build succeeds with no errors.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/views/HomeView.vue
git commit -m "feat: add denied SC/GR section to WorkBench top"
```

---

### Task 4: Tests — Workbench denied visibility

**Files:**
- Modify: `tests/test_query_service.py`

- [ ] **Step 1: Add import for `deny_sc`**

Add to the imports at the top of `tests/test_query_service.py`:

```python
from sc_gr_app.services.sc_service import approve_sc, create_sc, create_sc_draft, add_sc_vendor, deny_sc
```

(Replace the existing `approve_sc, create_sc, create_sc_draft, add_sc_vendor` import line.)

- [ ] **Step 2: Add import for `deny_gr`**

Add to the existing gr_service import line:

```python
from sc_gr_app.services.gr_service import approve_gr, create_gr, deny_gr
```

- [ ] **Step 3: Write test — denied SC appears for requester and admin sees all**

Add after existing workbench tests:

```python
def test_workbench_denied_sc_visibility(app_config):
    """Requester sees own denied SCs; admin sees all denied SCs."""
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    # USER1 creates and submits an SC
    sc1 = create_sc(
        app_config, USER,
        {"sc_no": "SC-U1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    deny_sc(app_config, ADMIN, sc1["sc_id"])

    # USER2 creates and submits an SC
    sc2 = create_sc(
        app_config, OTHER_USER,
        {"sc_no": "SC-U2", "requester_id": "U2", "request_type": "service",
         "cost_center": 1002, "sc_amount": 500,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    deny_sc(app_config, ADMIN, sc2["sc_id"])

    # USER1 sees only own denied SC
    user1_data = workbench_data(app_config, USER)
    assert user1_data["sc"]["denied"]["count"] == 1

    # Admin sees both denied SCs
    admin_data = workbench_data(app_config, ADMIN)
    assert admin_data["sc"]["denied"]["count"] == 2

    # USER2 sees only own denied SC
    user2_data = workbench_data(app_config, OTHER_USER)
    assert user2_data["sc"]["denied"]["count"] == 1
```

- [ ] **Step 4: Write test — denied SC hidden from other requester**

```python
def test_workbench_denied_sc_hidden_from_other_requester(app_config):
    """A requester should NOT see another requester's denied SC."""
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    # USER2 creates and denies an SC
    sc = create_sc(
        app_config, OTHER_USER,
        {"sc_no": "SC-U2", "requester_id": "U2", "request_type": "service",
         "cost_center": 1002, "sc_amount": 500,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    deny_sc(app_config, ADMIN, sc["sc_id"])

    # USER1 should see zero denied SCs (they belong to USER2)
    user1_data = workbench_data(app_config, USER)
    assert user1_data["sc"]["denied"]["count"] == 0
```

- [ ] **Step 5: Write test — denied GR visibility**

```python
def test_workbench_denied_gr_visibility(app_config):
    """Requester sees own denied GRs; admin sees all denied GRs."""
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    # Create and approve SC + PO so GRs can be created
    sc = create_sc(
        app_config, USER,
        {"sc_no": "SC-1", "requester_id": "U1", "request_type": "service",
         "cost_center": 1001, "sc_amount": 1000,
         "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"},
    )
    approve_sc(app_config, ADMIN, sc["sc_id"])
    vendor = create_vendor(app_config, USER, {
        "vendor_name": "Vendor A", "ksrm_vendor_code": "VA-1",
        "service_scope": "General",
    })
    add_sc_vendor(app_config, ADMIN, sc["sc_id"], vendor["vendor_id"])
    po = create_po(app_config, ADMIN, {
        "sc_id": sc["sc_id"], "vendor_id": vendor["vendor_id"],
        "po_no": "PO-1", "po_amount": 800, "status": "active",
    })

    # USER1 creates and denies a GR
    gr1 = create_gr(
        app_config, USER,
        {"po_id": po["po_id"], "requester_id": "U1",
         "estimated_amount": 100, "status": "pending"},
    )
    deny_gr(app_config, ADMIN, gr1["gr_id"])

    # USER2 creates and denies a GR
    gr2 = create_gr(
        app_config, OTHER_USER,
        {"po_id": po["po_id"], "requester_id": "U2",
         "estimated_amount": 200, "status": "pending"},
    )
    deny_gr(app_config, ADMIN, gr2["gr_id"])

    # USER1 sees only own denied GR
    user1_data = workbench_data(app_config, USER)
    assert user1_data["gr"]["denied"]["count"] == 1
    assert len(user1_data["gr"]["denied"]["rows"]) == 1
    assert "denied_at" in user1_data["gr"]["denied"]["rows"][0]

    # Admin sees both denied GRs
    admin_data = workbench_data(app_config, ADMIN)
    assert admin_data["gr"]["denied"]["count"] == 2
```

- [ ] **Step 6: Run new tests**

```bash
cd c:/Users/V2SE7PP/Projects/contract && uv run pytest tests/test_query_service.py::test_workbench_denied_sc_visibility tests/test_query_service.py::test_workbench_denied_sc_hidden_from_other_requester tests/test_query_service.py::test_workbench_denied_gr_visibility -v
```

Expected: 3 PASS

- [ ] **Step 7: Run all workbench tests to confirm no regressions**

```bash
cd c:/Users/V2SE7PP/Projects/contract && uv run pytest tests/test_query_service.py -v -k "workbench"
```

Expected: All 7 workbench tests pass (4 existing + 3 new).

- [ ] **Step 8: Commit**

```bash
git add tests/test_query_service.py
git commit -m "test: add workbench denied SC/GR visibility tests"
```

---

## Verification

After all tasks are complete, run the full test suite:

```bash
cd c:/Users/V2SE7PP/Projects/contract && uv run pytest tests/ -v
```

Start the dev server and verify manually:

1. **No denied records** — WorkBench shows no denied section at top
2. **Denied SC exists** — denied section appears at top with SC cell showing count
3. **Denied GR exists** — denied section appears with GR cell
4. **Click denied SC cell** — navigates to `/sc?status=denied` showing filtered list
5. **Click denied GR cell** — navigates to `/gr?status=denied` showing filtered list
6. **Requester** — sees only own denied records
7. **Admin** — sees all denied records
