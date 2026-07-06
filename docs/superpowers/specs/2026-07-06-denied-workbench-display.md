# Denied SC/GR WorkBench Display

## Summary

被驳回 (denied) 的 SC 和 GR 记录无法在 WorkBench 展示，因为后端 `workbench_data` 状态列表缺少 `"denied"`，前端 `HomeView` 也未渲染 denied 状态的 cell。在 WorkBench 顶部条件性地展示 denied 记录。

## Backend

**File:** `sc_gr_app/services/query_service.py`

### 1. Add `"denied"` to status lists

```python
# line 653
sc_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
# line 655
gr_statuses = ["draft", "manager_confirm", "pending", "approved", "denied"]
```

### 2. Update `_is_own_only` visibility

Add `"denied"` to the exclusion set so admins see all denied records (not just their own):

```python
# line 664
return status not in ("pending", "active", "manager_confirm", "approved", "denied")
```

### 3. SC query SELECT additions

SC does not have `denied_by`/`denied_at` columns. Show `updated_at` as the denied timestamp:

```python
# Add to the SC SELECT (line 683-687)
"sc.updated_at AS denied_at, "
```

### 4. GR query SELECT additions

GR has `denied_by`/`denied_at` columns:

```python
# Add to the GR SELECT (line 752-756)
"gr.denied_by, gr.denied_at, "
```

## Frontend

**File:** `frontend/src/views/HomeView.vue`

### 1. New denied section (template, placed above existing WorkBench)

```html
<div class="wb-section" v-if="deniedScCount > 0 || deniedGrCount > 0">
  <h3 class="wb-section__title">{{ $t('workbench.denied') }}</h3>
  <div class="wb-grid">
    <div class="wb-cell" v-if="deniedScCount > 0" @click="goToScList('denied')">
      <span class="wb-cell__status wb-cell__status--denied">{{ $t('status.denied') }}</span>
      <span class="wb-cell__count">{{ deniedScCount }}</span>
      <span class="wb-cell__unit">{{ $t('workbench.items') }}</span>
    </div>
    <div class="wb-cell" v-if="deniedGrCount > 0" @click="goToGrList('denied')">
      <span class="wb-cell__status wb-cell__status--denied">{{ $t('status.denied') }}</span>
      <span class="wb-cell__count">{{ deniedGrCount }}</span>
      <span class="wb-cell__unit">{{ $t('workbench.items') }}</span>
    </div>
  </div>
</div>
```

### 2. New computed properties

```javascript
const deniedScCount = computed(() => data.value.sc?.denied?.count ?? 0)
const deniedGrCount = computed(() => data.value.gr?.denied?.count ?? 0)
```

### 3. `headStatus` addition

```javascript
// line 227 in existing function
if (status.includes('denied')) return 'denied'
```

## Visibility Rules

| Role      | Denied SC            | Denied GR            |
|-----------|----------------------|----------------------|
| Requester | Own records only     | Own records only     |
| Admin     | All denied records   | All denied records   |

## Conditional Display

Denied section only renders when at least one denied record exists (SC or GR count > 0). Clicking a cell navigates to the corresponding list view filtered by denied status.

## Translation

Existing `status.denied` key is already used by ScListView and GrListView filters. New key `workbench.denied` for the section title (e.g., "已驳回").

## Scope

- SC: denied only (not finished/closed)
- GR: denied only (not finished)
- PO: out of scope (no deny flow for PO)
