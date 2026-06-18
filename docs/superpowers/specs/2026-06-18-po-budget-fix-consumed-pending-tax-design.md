# PO Budget Calculation: Fix consumed_amount & Add Pending Tax Field

## Problem

1. **`consumed_amount` is wrong**: Currently computed as `pending_total + con_value_total`, mixing Net Cost of unapproved GRs with Gross Cost of approved GRs. Should be only approved GRs' `con_value` (Gross Cost), since unapproved GRs haven't actually consumed budget.

2. **Missing `pending_total_incl_tax`**: No field captures the tax-inclusive estimated cost of pending (unapproved) GRs. Email recipients and PO detail viewers can't see what the upcoming tax-inclusive liability is.

3. **`manager_confirm` gap**: `query_service.py` GR totals subquery and `po_service.py` `_po_gr_usage` only count `status = 'pending'`, missing `manager_confirm`. This is inconsistent with `budget_service.py` and `sender.py` which correctly use `status IN ('pending', 'manager_confirm')`.

## Three budget fields (per PO)

| Display name (CN) | Internal key | Formula |
|---|---|---|
| 已消费金额 | `consumed_amount` | `SUM(con_value) WHERE status = 'approved'` |
| 待批准预估消费金额（不含税） | `po_pending_total` | `SUM(estimated_amount) WHERE status IN ('pending', 'manager_confirm')` |
| 待批准预估消费金额（含税） | `po_pending_total_incl_tax` | `SUM(estimated_amount * (1 + COALESCE(tax_rate, 0)/100)) WHERE status IN ('pending', 'manager_confirm')` |

GRs with NULL `tax_rate` contribute 0 to the tax portion, matching the existing behavior in `approve_gr` where NULL tax_rate requires explicit `con_value` input.

Cancelled and draft GRs are excluded from all three fields.

## Changes

### Backend

**`budget_service.py`** — Add `po_pending_total_incl_tax` and `sc_pending_total_incl_tax`:

- `compute_po_budget_decimal`: new SQL column `coalesce(sum(case when status in ('pending', 'manager_confirm') then estimated_amount * (1 + coalesce(tax_rate, 0) / 100.0) else 0 end), 0)` as `pending_total_incl_tax`
- `compute_sc_budget_decimal`: same pattern aggregated across all GRs under the SC
- Both return dicts gain `po_pending_total_incl_tax` / `sc_pending_total_incl_tax`

**`sender.py`** — Three changes in `_attach_budget_info` and `_attach_child_pos`:

1. Fix `consumed_amount = approved` (was `pending + approved`)
2. Add `pending_total_incl_tax` from new SQL query
3. `_attach_budget_info` for SC: fix `consumed_amount` similarly, add `sc_pending_total_incl_tax`

SQL for PO budget in `_attach_budget_info` changes from:
```sql
SELECT
  COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm') THEN estimated_amount ELSE 0 END), 0) AS pending_total,
  COALESCE(SUM(CASE WHEN status = 'approved' THEN con_value ELSE 0 END), 0) AS con_value_total
FROM gr_requests WHERE po_id = ?
```
to:
```sql
SELECT
  COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm') THEN estimated_amount ELSE 0 END), 0) AS pending_total,
  COALESCE(SUM(CASE WHEN status = 'approved' THEN con_value ELSE 0 END), 0) AS con_value_total,
  COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm') THEN estimated_amount * (1 + COALESCE(tax_rate, 0) / 100.0) ELSE 0 END), 0) AS pending_total_incl_tax
FROM gr_requests WHERE po_id = ?
```

**`query_service.py`** — `search_pos` GR totals subquery:

- Fix: `status = 'pending'` → `status IN ('pending', 'manager_confirm')`
- Add: `pending_total_incl_tax` column

**`po_service.py`** — `_po_gr_usage`:

- Fix: `status IN ('pending', 'approved')` → `status IN ('pending', 'manager_confirm', 'approved')`
- Treat `manager_confirm` same as `pending` (use `estimated_amount`)

**`sc_service.py`** — `get_sc_detail`:

- Already calls `compute_po_budget()` per PO, so `po_pending_total_incl_tax` flows through automatically
- Add `po["pending_total_incl_tax"] = po["budget"]["po_pending_total_incl_tax"]` to make it explicit on the PO dict

**`templates.py`** — `_po_fields` and `_child_po_table`:

- `_po_fields`: Replace single `consumed_amount` row with three rows:
  - Consumed Amount (consumed_amount)
  - Pending Est. Amount excl. Tax (po_pending_total / pending_total)
  - Pending Est. Amount incl. Tax (pending_total_incl_tax)
- `_child_po_table`: Add pending_total_incl_tax column, rename Consumed → only approved
- `_child_gr_table`: Add tax_rate and pending_total_incl_tax info

### Frontend

**`PoDetailView.vue`** — Add three description items after `po.open_po_amount`:

```html
<el-descriptions-item :label="$t('po.consumedAmount')"><AmountDisplay :value="po.consumed_amount" /></el-descriptions-item>
<el-descriptions-item :label="$t('po.pendingExclTax')"><AmountDisplay :value="po.pending_total || po.budget?.po_pending_total" /></el-descriptions-item>
<el-descriptions-item :label="$t('po.pendingInclTax')"><AmountDisplay :value="po.pending_total_incl_tax || po.budget?.po_pending_total_incl_tax" /></el-descriptions-item>
```

**i18n** — New keys for zh-CN and en-US:

```js
// zh-CN
po: {
  consumedAmount: '已消费金额',
  pendingExclTax: '待批准预估消费金额（不含税）',
  pendingInclTax: '待批准预估消费金额（含税）',
}

// en-US
po: {
  consumedAmount: 'Consumed Amount',
  pendingExclTax: 'Pending Est. Amount (excl. tax)',
  pendingInclTax: 'Pending Est. Amount (incl. tax)',
}
```

### Edge cases

- **NULL tax_rate**: treated as 0% — incl_tax = excl_tax. Consistent with `approve_gr` behavior.
- **No GRs under PO**: all three fields are 0.
- **All GRs approved**: `pending_total = 0`, `pending_total_incl_tax = 0`, `consumed_amount = SUM(con_value)`.
- **All GRs pending/manager_confirm**: `consumed_amount = 0`, `pending_total = SUM(estimated_amount)`, `pending_total_incl_tax` = sum with tax.
- **Draft GRs**: excluded from all calculations (not pending/manager_confirm, not approved).
- **Cancelled GRs**: excluded from all calculations.
- **Approved GR with NULL con_value**: already guarded by existing NULL check that raises `ConflictError`.
- **Decimal precision**: all calculations use Python `Decimal` to avoid float errors.

## Not in scope

- SC-level consumed_amount display in SC detail UI (only PO detail is requested)
- Monthly summary email changes (uses `open_po_amount` only, no consumed amount)
