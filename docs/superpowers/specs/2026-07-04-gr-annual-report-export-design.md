# GR Annual Report Export — Design Spec

**Date:** 2026-07-04
**Status:** Approved

## Overview

Add an "Export Annual Report" button to the GR List view. The user picks a year, and the system exports an Excel file containing all GRs with status `approved` or `finished` within that year, formatted per the EGV_2025 sheet template in `docs/GR Checking list.xlsx`.

## Flow

```
GR List → click "年报导出" → year picker dialog → confirm
→ call get_gr_annual_report API → build Excel in frontend → save_file
```

## Backend: New Endpoint

**Method:** `get_gr_annual_report`

**Input:** `{ year: "2026" }`

**Logic:**
- Query `gr_requests` WHERE `status IN ('approved', 'finished')`
- For `finished` GRs: filter by `strftime('%Y', finished_at) = year`
- For `approved` GRs: filter by `strftime('%Y', approved_date) = year`
- JOIN `pos` (po_no, sc_id), `sc_records` (sc_no, cost_center), `vendors` (vendor_name), `users` (requester_name)
- Return flat array of enriched GR objects

**Return:** `{ rows: [...] }` — each row has all GR fields + `po_no`, `sc_no`, `cost_center`, `vendor_name`, `requester_name`

## Frontend: UI

**Button:** New "年报导出" button in `GrListView.vue`, placed after the existing Export button.

**Dialog:** Simple `el-dialog` with:
- Title: "导出年报"
- `el-date-picker` with `type="year"`, default current year
- Confirm button with loading state

**File name:** `GR_Annual_Report_<year>.xlsx`

## Excel Columns (in order)

| # | Column Header | Data Field | Notes |
|---|--------------|-----------|-------|
| 1 | cost center | `cost_center` | From SC via PO |
| 2 | Status | `status` | finished→"Finished", approved→"Approved" |
| 3 | PO number | `po_no` | |
| 4 | Confirmation number | `confirmation_name` | |
| 5 | GR NO | `gr_no` | |
| 6 | GR Value | `con_value` | |
| 7 | GR Description | `goods_service_description` | |
| 8 | GR Requester | `requester_name` | |
| 9 | Finished Date | `finished_at` | Empty for approved GRs |
| 10 | provision | — | Always empty |
| 11 | Provision amount NET | — | Always empty |
| 12+ | (all remaining GR fields) | raw field name | Includes estimated_amount, gross_cost, tax_rate, sc_no, vendor_name, remark, delivery_from, delivery_to, last_delivery, created_at, approved_date, etc. Column header uses the raw DB field name. |

**Excluded from output:** `dIfference` column (per user request).

## Files to Modify

| File | Change |
|------|--------|
| `frontend/src/views/GrListView.vue` | Add button + year picker dialog + export handler |
| `frontend/src/i18n/locales/zh-CN.js` | Add i18n keys |
| `frontend/src/i18n/locales/en-US.js` | Add i18n keys |
| `sc_gr_app/api/bridge.py` | New `get_gr_annual_report` endpoint |
| `sc_gr_app/services/gr_service.py` | New query function |

## Error Handling

- API failure: show `ElMessage.error` with the error message
- Empty result: still export an Excel file with headers only (no data rows)
- Invalid year: backend validates year format, returns 400 on bad input

## Testing

- Unit test: `test_get_gr_annual_report` — verify query filters by year and status correctly
- Unit test: verify JOIN chain resolves cost_center, vendor_name, requester_name correctly
