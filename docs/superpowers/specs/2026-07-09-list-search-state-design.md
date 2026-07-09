# List Search State Design

## Context

The PO, SC, GR, and Vendor list pages currently use similar search UI patterns but do not share one search state model. Search and advanced filters can be lost when paging, sorting, refreshing after mutations, or exporting. Vendor listing also lacks pagination and can silently show/export only the backend default result set.

This design introduces one shared list-search state model for PO, SC, GR, and Vendor pages.

## Goals

- Keep search text, advanced filters, sorting, pagination, rows, total, loading, and error state in one place per list.
- Preserve current search/filter state across paging, sorting, save, import, batch actions, export, refresh, and route restoration.
- Synchronize list state to URL query parameters so the same list view can be refreshed or shared.
- Make advanced text filters fuzzy-match by default.
- Add Vendor pagination and make Vendor export use the current filtered result set.
- Keep GR annual report export independent from list search state.

## Non-Goals

- Redesigning the visual layout of the filter bar.
- Adding a separate Apply button. Search and filters remain auto-applied.
- Changing GR annual report export behavior.
- Replacing the backend search service with full-text search in this iteration.

## Architecture

Add a shared frontend composable, tentatively named `useListSearch`, used by `usePo`, `useSc`, `useGr`, and `useVendor`.

The composable owns:

- `text`
- `filters`
- `sort`
- `direction`
- `currentPage`
- `pageSize`
- `rows`
- `total`
- `loading`
- `error`

The composable is configured with:

- API name, such as `search_pos`, `search_scs`, `search_grs`, or `search_vendors`
- default sort and direction
- default page size
- allowed URL filter keys for the list
- optional filter transformation, such as deadline shortcuts

## Data Flow

On page mount:

1. Read URL query parameters.
2. Restore `text`, filters, sorting, direction, page, and page size.
3. Reflect restored values into `AdvancedFilterBar`.
4. Query the backend using the restored state.

When the user searches or changes filters:

1. Update `text` and filters.
2. Reset `currentPage` to 1.
3. Sync URL query parameters.
4. Query the backend.
5. Clear selected rows for pages that support selection.

When the user changes page or page size:

1. Update pagination state.
2. Sync URL query parameters.
3. Query using the current search text and filters.
4. Clear selected rows.

When the user changes sorting:

1. Update sort and direction.
2. Reset `currentPage` to 1.
3. Sync URL query parameters.
4. Query using the current search text and filters.
5. Clear selected rows.

When data is saved, imported, or changed through batch actions:

1. Call `reload()`.
2. Query using the current state without clearing search/filter state.

## URL Query Contract

Use flat query parameters:

- `q` for the search box text
- `page`
- `pageSize`
- `sort`
- `direction`
- advanced filters as direct keys, for example `status=approved`, `vendor_name=abc`, `po_amount_min=1000`

Rules:

- Empty values are omitted from the URL.
- Existing `?status=...` entry points remain supported.
- Invalid `page` or `pageSize` values fall back to defaults.
- Unknown filter keys are ignored on restore and are not sent to the backend.
- Query updates should not create noisy browser history entries during debounced typing; replace navigation is preferred for state sync.

## Filter Semantics

Search box:

- Continues to use backend multi-column fuzzy search.

Advanced text inputs:

- Use fuzzy matching by default.
- Applies to IDs, numbers stored as text, names, requester/creator fields, cost center, purchaser, descriptions, contact fields, and similar text fields.

Structured filters:

- Select filters remain exact matches.
- Amount filters remain min/max ranges.
- Date filters remain from/to ranges.
- Deadline shortcut filters are converted to date ranges before querying.
- Deadline date generation must use local date formatting instead of UTC `toISOString()` slicing.

Backend search services keep whitelist validation as a safety boundary.

## Page Behavior

PO, SC, and GR:

- Use `useListSearch` for all list queries.
- Paging does not lose current search/filter state.
- Sorting is server-side and reloads data.
- Filtering and sorting reset to page 1.
- Save, import, and batch actions call `reload()`.
- Selected rows clear after search, filter, page, page size, sort, and reload transitions.

Vendor:

- Gains pagination and total count handling.
- Uses `vendor_name asc` as the default sort.
- Uses the same URL and search state behavior as PO, SC, and GR.
- Existing Vendor export changes from exporting `state.rows` to exporting the current filtered result set.

## Export Behavior

For normal PO, SC, and GR export:

- If rows are selected, export selected rows.
- If no rows are selected, export all rows matching the current search/filter state.
- Sorting and direction are passed from the current list state.

For Vendor export:

- The current Vendor page has no row-selection UI.
- Export all rows matching the current search/filter state.
- Sorting and direction are passed from the current list state.

GR annual report export:

- Remains independent from list search/filter state.

## Error Handling

- Query failure preserves current URL and search state.
- Query failure clears current `rows` and records `state.error`.
- Invalid pagination values in URL fall back to defaults.
- Unknown filter keys in URL are ignored.
- Backend field whitelist validation remains in place for defense in depth.
- Export errors continue to use existing message behavior.

## Testing

Backend tests:

- Add or update query service tests for fuzzy advanced text filters across PO, SC, GR, and Vendor.
- Include representative fields such as PO number, vendor name, cost center, requester name, GR description, Vendor name, KSRM code, and contact/email fields.

Frontend tests:

- Verify `applyFilter` stores text and filters, resets to page 1, syncs URL, and queries.
- Verify `changePage` and `changePageSize` keep current text and filters.
- Verify `changeSort` sets sort/direction, resets to page 1, syncs URL, and queries.
- Verify URL query initializes list state and reflected filter-bar values.
- Verify `reset` clears search/filter query parameters.
- Verify selected rows are cleared after list state transitions.

Verification commands:

- `uv run pytest tests/test_query_service.py tests/test_query_filters.py`
- Any added frontend JS tests
- `npm.cmd run build`

## Implementation Notes

- Keep the first implementation focused on search state, URL sync, Vendor pagination, export input correctness, and fuzzy filter semantics.
- Avoid visual redesign in this iteration.
- Keep backend query whitelist explicit; do not infer arbitrary URL keys into SQL filters.
