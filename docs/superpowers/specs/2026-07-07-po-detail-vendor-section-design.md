# PO Detail Vendor Section & Independent FC PO Vendor Optionality

**Date**: 2026-07-07
**Status**: Approved

## Background

Three related improvements to PO Detail:

1. PO Detail lacks a vendor information section comparable to SC Detail's `ScVendorSection`
2. Vendor selection dropdown shows no data for FC POs without upstream SC (scVendors is empty)
3. Independent FC POs (no upstream SC) should be allowed to have no vendor

## Design

### 1. PO Detail: Reuse ScVendorSection

**File**: `frontend/src/views/PoDetailView.vue`

- Import and render `ScVendorSection` in PO Detail, placed between budget card and process summary
- Build `poVendorList` computed: wraps PO's single vendor (from `po.vendor_id`/`po.vendor_name`) into an array. When `po.vendor_id` is null/empty, the array is empty and the empty state displays naturally.
- Pass `:can-manage="false"` (vendor add/remove on PO is handled via the edit form, not inline)

### 2. Fix Vendor Dropdown Bug

**File**: `frontend/src/views/PoDetailView.vue`

- `PoFormDialog` `:vendors` attr: `hasSc ? scVendors : vendors`
  - With SC: use SC's vendor list (scoped)
  - Without SC (independent PO): use full vendor list from `searchVendors()`

### 3. Allow Independent FC PO to Have No Vendor

**Frontend**:
- `PoFormDialog.vue`: new `vendorRequired` prop (default `true`). When `false`, remove `vendor_id` from form validation rules.
- `PoDetailView.vue`: pass `:vendor-required="hasSc"` to `PoFormDialog` (required only when PO belongs to an SC)

**Backend**:
- `bridge.py` `get_po_detail`: change `join vendors` to `left join vendors` so POs with NULL `vendor_id` still return successfully (vendor fields will be null)

## Scope

| File | Change |
|------|--------|
| `frontend/src/views/PoDetailView.vue` | Add ScVendorSection, fix vendor dropdown logic, conditional vendor-required |
| `frontend/src/components/po/PoFormDialog.vue` | Add vendorRequired prop, conditional validation rule |
| `sc_gr_app/api/bridge.py` | `get_po_detail`: INNER JOIN -> LEFT JOIN on vendors |
