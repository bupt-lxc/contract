# Spec: GR Import — Relax Required Fields & Remove Delivery Fields

Date: 2026-07-08
Branch: feat/independent-fc-po

## Summary

Two changes:

1. **Import validation**: `estimated_amount` (Net Cost) is no longer required during GR import. Imported GRs must be `approved` or `finished` status, so budget/pending paths are unaffected. All null-encountering code paths treat null `estimated_amount` as 0 defensively.
2. **Remove `delivery_from` / `delivery_to`**: Removed from the entire system — frontend (form, detail, list, export), i18n, backend CRUD, import, query service, export service, notification templates.

Database columns are left in place (SQLite DDL compatibility), but no new code writes to them.

## Changes

### Part 1: Import Relaxation

**`sc_gr_app/services/import_service.py`**

- `_GR_COLUMN_ALIASES` (L53-68): Remove `delivery_from` and `delivery_to` alias entries.
- `_validate_gr_rows` (L543): Remove `estimated_amount`, `delivery_from`, `delivery_to` from required-fields check. Keep `po_no`, `gr_no`, `con_value`, `status`. Valid statuses must include `approved` and `finished`.
- `preview_gr_import` (L746): Same required-fields change.
- `import_grs` INSERT (L820-846): Remove `delivery_from`, `delivery_to` columns from INSERT and value list.

**Defensive null-safety (unrelated to import flow, but guards against future null `estimated_amount`):**

- `sc_gr_app/services/gr_service.py`:
  - `submit_gr` (L459): `Decimal(str(before["estimated_amount"] or 0))`
  - `approve_gr` (L588): `Decimal(str(before["estimated_amount"] or 0))`
  - `update_gr` pending path (L707-708): `_positive_number` validates `estimated_amount` is still required for form-created GRs — no change needed.
- `sc_gr_app/services/sc_service.py` (L441): `Decimal(str(row["estimated_amount"] or 0))`
- `sc_gr_app/services/budget_service.py` (L148, L238, L300): Change `then estimated_amount` to `then coalesce(estimated_amount, 0)` in pending_total subqueries for PO budget.
- `sc_gr_app/notification/sender.py` (L56): Same COALESCE fix in the PO budget subquery.

### Part 2: Remove delivery_from / delivery_to System-Wide

**Frontend:**

| File | Change |
|------|--------|
| `frontend/src/components/po/GrFormDialog.vue` | Remove date-picker rows (L71-82), remove fields from `emptyForm()` |
| `frontend/src/views/GrDetailView.vue` | Remove delivery_from/to display rows (L49-50) |
| `frontend/src/views/GrListView.vue` | Remove table columns (L70-75), filter config (L283-284), sort config (L522-523) |
| `frontend/src/components/export/ExportDialog.vue` | Remove delivery_from/to export columns (L170-171) |
| `frontend/src/views/PoDetailView.vue` | Remove delivery_from/to export columns (L487-488) |
| `frontend/src/i18n/locales/zh-CN.js` | Remove `deliveryFrom`, `deliveryTo` keys |
| `frontend/src/i18n/locales/en-US.js` | Remove `deliveryFrom`, `deliveryTo` keys |

**Backend:**

| File | Change |
|------|--------|
| `sc_gr_app/services/gr_service.py` create_gr | Remove `delivery_from`, `delivery_to` from INSERT column/value lists |
| `sc_gr_app/services/gr_service.py` update_gr draft/pending | Remove from allowed keys, UPDATE SET columns, and value list |
| `sc_gr_app/services/gr_service.py` update_gr approved | Remove from allowed keys, UPDATE SET columns, and value list |
| `sc_gr_app/services/query_service.py` | Remove `delivery_from`, `delivery_to` from `text_columns` (L567-568), `allowed_filters` and range variants (L598-603), `allowed_sorts` (L640-641) |
| `sc_gr_app/services/export_service.py` | Remove `delivery_from`, `delivery_to` from export column definitions (check `_gr_overview` and any other GR export sections) |
| `sc_gr_app/services/import_service.py` | Remove from `_GR_COLUMN_ALIASES`, INSERT statement |
| `sc_gr_app/notification/templates.py` | Remove `delivery_from`, `delivery_to` from `_GR_ORDER` list (L118-121) |
| `sc_gr_app/notification/sender.py` | Remove `delivery_from`, `delivery_to` from `_attach_child_grs` SELECT (L187-188) |

### Database

No schema migration needed. Columns `delivery_from`, `delivery_to` remain in `gr_requests` table but are no longer written by application code.

### Not Changing

- `REQUIRED_FIELDS` in `gr_service.py` L18 stays `("po_id", "requester_id", "estimated_amount")` — the frontend form path still requires `estimated_amount`. Only the import path is relaxed.
- `export_service.py` aggregate `sum(estimated_amount)` — imported GRs are approved/finished, so this sums `estimated_amount` (which may be null → 0). The approved-GR budget uses `con_value` not `estimated_amount`, so this is informational only and does not affect budget correctness.
