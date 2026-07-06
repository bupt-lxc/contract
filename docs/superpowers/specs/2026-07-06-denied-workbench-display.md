# Denied SC/GR WorkBench Display

## Summary

被驳回 (denied) 的 SC 和 GR 记录无法在 WorkBench 展示，因为后端 `workbench_data` 状态列表缺少 `"denied"`，前端 `HomeView` 也未渲染 denied 状态的 cell。在 WorkBench 顶部条件性地展示 denied 记录。

## Backend

**File:** `sc_gr_app/services/query_service.py`

### 1. Add `"denied"` to status lists

```python
sc_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
gr_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
```

### 2. Update `_is_own_only` visibility

Add `"denied"` to the exclusion set so admins see all denied records:

```python
return status not in ("pending", "active", "manager_confirm", "approved", "denied")
```

### 3. GR query SELECT additions

GR has `denied_by`/`denied_at` columns. Add them to the SELECT (after `gr.submitted_date`):

```python
"gr.denied_by, gr.denied_at, "
```

### 4. SC query — no SELECT changes needed

SC does not have `denied_by`/`denied_at` columns and the WorkBench display does not render a denied timestamp for SC. The existing SELECT fields are sufficient.

## Frontend

**File:** `frontend/src/views/HomeView.vue`

### 1. New denied section (template, placed above existing workbench content)

Follow existing BEM conventions and inline `$router.push` pattern used by every other cell:

```html
<div class="wb-section" v-if="deniedScCount > 0 || deniedGrCount > 0">
  <h3 class="wb-section__title">{{ $t('home.denied') }}</h3>
  <div class="wb-grid">
    <div
      v-if="deniedScCount > 0"
      class="wb-cell wb-cell--denied"
      @click="$router.push('/sc?status=denied')"
    >
      <div class="wb-cell__head wb-cell__head--denied">
        <span class="wb-cell__head-text">{{ $t('status.denied') }}</span>
        <span class="wb-cell__head-badge">{{ deniedScCount }}</span>
      </div>
    </div>
    <div
      v-if="deniedGrCount > 0"
      class="wb-cell wb-cell--denied"
      @click="$router.push('/gr?status=denied')"
    >
      <div class="wb-cell__head wb-cell__head--denied">
        <span class="wb-cell__head-text">{{ $t('status.denied') }}</span>
        <span class="wb-cell__head-badge">{{ deniedGrCount }}</span>
      </div>
    </div>
  </div>
</div>
```

### 2. New computed properties

Place alongside existing `scRow1`, `scRow2`, etc. in `<script setup>`:

```javascript
const deniedScCount = computed(() => data.value.sc?.denied?.count ?? 0)
const deniedGrCount = computed(() => data.value.gr?.denied?.count ?? 0)
```

### 3. `headStatus` addition

Insert before the fallback `return 'draft'`:

```javascript
if (status.includes('denied')) return 'denied'
```

### 4. New CSS rules

Add alongside existing `wb-cell__head--draft`, `wb-cell__head--pending`, etc.:

```css
.wb-section {
  margin-bottom: 16px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
}
.wb-section__title {
  font-size: 14px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 12px;
}
.wb-cell__head--denied {
  background: #fef2f2;
}
.wb-cell--denied .wb-cell__table {
  background: #fefaf9;
}
```

The red tint follows the existing `--status-denied: #ef4444` CSS variable defined in `frontend/src/assets/main.css`.

## i18n

**File:** `frontend/src/i18n/locales/zh-CN.js` and `frontend/src/i18n/locales/en-US.js`

Add under the `home` namespace (alongside existing `home.workbench`, `home.scNo`, etc.):

| Key | zh-CN | en-US |
|-----|-------|-------|
| `home.denied` | `已驳回` | `Denied` |

Existing `status.denied` (已拒绝 / Denied) is already used by ScListView and GrListView filters — no change needed.

## Visibility Rules

| Role      | Denied SC            | Denied GR            |
|-----------|----------------------|----------------------|
| Requester | Own records only     | Own records only     |
| Admin     | All denied records   | All denied records   |

## Conditional Display

Denied section only renders when at least one denied record exists (SC or GR count > 0). Clicking a cell navigates to the corresponding list view filtered by denied status (both ScListView and GrListView already support `?status=denied` query parameter filtering).

## Notification

No new notification logic needed. The existing `_auto_open_outlook_draft("sc", sc_id, "deny")` and `_auto_open_outlook_draft("gr", gr_id, "deny")` in `bridge.py` already trigger denial emails. The `notification_service.py` already queues `status_change` entries for the `'deny'` transition.

## Tests

**File:** `tests/test_query_service.py`

Existing workbench_data tests check `approved`/`pending` statuses only and will not break. Add these test cases:

1. **Denied SC appears for requester** — seed a denied SC where `requester_id = current_user`, assert workbench_data includes it in `sc.denied`
2. **Denied SC hidden from other requester** — seed a denied SC owned by user B, call workbench_data as user A (requester), assert `sc.denied.count == 0`
3. **Admin sees all denied SCs** — seed denied SCs from multiple users, call as admin, assert `sc.denied.count` matches total
4. **Denied GR appears for requester** — mirror of case 1 for GR
5. **Admin sees all denied GRs** — mirror of case 3 for GR

## Scope

- SC: denied only (not finished)
- GR: denied only (not finished)
- PO: out of scope (no deny flow for PO)
