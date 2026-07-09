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
- Migrating Operation Logs or Email Logs to `useListSearch`. They remain out of scope for this change.

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
- allowed backend sort keys for the list
- optional filter transformation, such as deadline shortcuts

The composable returns:

- `state`
- `initializeFromRoute()`
- `applyFilter({ text, filters })`
- `changePage(page)`
- `changePageSize(size)`
- `changeSort({ prop, order })`
- `reset()`
- `reload()`

Existing names `searchScs`, `searchPos`, `searchGrs`, and `searchVendors` remain as compatibility aliases. They must update and use the shared state rather than performing stateless one-off searches.

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
2. Preserve `text`, filters, sort, direction, page, and page size.
3. Clear selected rows.
4. Query using the current state.

Browser back/forward behavior:

1. If route query changes while the user stays on the same list route, parse the new query.
2. Update the shared list state and visible filter controls.
3. Re-run the query with the restored state.

## AdvancedFilterBar Contract

`AdvancedFilterBar` becomes controlled by its parent list page.

- It exposes `v-model:text` for the search box.
- It exposes `v-model:filters` for advanced filter values.
- It emits filter changes after debounced text input and immediately after structured filter changes.
- It watches parent model changes so URL-restored values are visible in the input controls.
- If restored filters are non-empty, the advanced filter panel opens automatically.
- Reset clears both the parent model and internal controls.
- Text search debounce is 500 ms.

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
- Existing PO, SC, and GR list entry points with `?status=...` remain supported and restore the visible status advanced filter.
- Invalid `page` or `pageSize` values fall back to defaults.
- Invalid `sort` values fall back to the list default sort.
- Invalid `direction` values fall back to the list default direction.
- Unknown filter keys are ignored on restore and are not sent to the backend.
- Query updates use `router.replace`, not `router.push`, for search, filter, page, page size, and sort changes.
- URL keys are frontend-only. Before API calls, `q` is translated to `text`, and `page`/`pageSize` are translated to `limit`/`offset`.
- Reserved non-filter query keys are never sent to backend filters: `q`, `page`, `pageSize`, `sort`, `direction`, `redirect`, `returnTo`, `highlight`, and `action`.

## Filter Semantics

Search box:

- Continues to use backend multi-column fuzzy search.

Advanced text inputs:

- Use case-insensitive contains matching.
- SQL wildcard input is treated as literal user input. Advanced text filters are parameterized and escape LIKE wildcards `%`, `_`, and the escape character before building contains-match parameters.
- Fuzzy fields are explicitly whitelisted per entity:
  - PO: `po_id`, `po_no`, `sc_id`, `vendor_id`, `vendor_name`, `requester_name`, `contract_no`, `payment_frequency`, `contract_pos`, `cost_center`, and `purchaser`.
  - SC: `sc_id`, `sc_no`, `requester_id`, `requester_name`, `created_by`, `created_by_name`, `cost_center`, `description`, `calloff_po_id`.
  - GR: `gr_id`, `gr_no`, `po_id`, `sc_id`, `requester_id`, `vendor_id`, `goods_service_description`, `confirmation_name`, and `remark`.
  - Vendor: `vendor_id`, `vendor_name`, `ksrm_vendor_code`, `company_name_cn`, `service_scope`, `created_by`, `contact_person`, `email`, `phone`, and `description`.

Structured filters:

- Select filters remain exact matches.
- Amount filters remain min/max ranges.
- Date filters remain from/to ranges.
- Deadline shortcut filters support the existing values `3y`, `2y`, `1y`, `6m`, `5m`, `4m`, `3m`, `2m`, and `1m`.
- Deadline shortcuts convert to inclusive `deadline_from` and `deadline_to` local `YYYY-MM-DD` strings.
- `deadline_from` is the user's local current date.
- `deadline_to` is the local current date plus the selected duration.
- Deadline date generation must use a shared local-date helper instead of UTC `toISOString()` slicing.

Backend search services keep whitelist validation as a safety boundary.

## Page Behavior

PO, SC, and GR:

- Use `useListSearch` for all list queries.
- Paging does not lose current search/filter state.
- Sorting is server-side and reloads data.
- PO table columns that remain sortable must emit `sort-change` and use Element Plus custom sorting instead of current-page local sorting.
- Derived columns are sortable only if they are present in the backend allowed sort whitelist; otherwise they must not present a sortable UI.
- Filtering and sorting reset to page 1.
- Save, import, and batch actions call `reload()`.
- Selected rows clear after search, filter, page, page size, sort, and reload transitions.

Vendor:

- Gains pagination and total count handling.
- Uses the same pagination layout as PO, SC, and GR.
- Uses page size 10.
- Uses `vendor_name asc` as the default sort.
- Supports server-side sort change for sortable Vendor columns.
- Uses the same URL and search state behavior as PO, SC, and GR.
- Existing Vendor export changes from exporting `state.rows` to exporting the current filtered result set.
- Create, update, disable, delete, and import completion call `reload()`.

## Export Behavior

Export payloads use the same normalized criteria as the visible list:

- `text`
- `filters`
- `sort`
- `direction`
- `selected_ids`

For "all matching rows", `page` and `pageSize` are intentionally omitted from the export criteria.

For normal PO, SC, and GR export:

- If rows are selected, export selected rows.
- If no rows are selected, export all rows matching the current search/filter state.
- Sorting and direction are passed from the current list state.
- `ExportDialog` and the backend export bridge must pass and honor `text`, not only `filters`.
- Export rows and export statistics must use the same normalized criteria, including text search.

For Vendor export:

- The current Vendor page has no row-selection UI.
- Export all rows matching the current search/filter state.
- Sorting and direction are passed from the current list state.
- Vendor export must fetch all matching rows through the search API or an equivalent export path using `text`, filters, sort, and direction. It must not export only the currently loaded page.

GR annual report export:

- Remains independent from list search/filter state.

## Navigation Compatibility

Workbench/dashboard links:

- Existing workbench links that navigate to PO, SC, or GR lists with `?status=...` are canonical list-entry URLs and remain supported.
- The status query restores the visible status filter and participates in the shared list state.

Detail navigation:

- When a list page opens a detail page, it includes a safe same-app `returnTo` query value containing the current list full path.
- Detail pages that finish/delete/cancel and need to return to a list use `returnTo` when present; otherwise they use their current fallback route.
- Direct detail links from email or external deep links do not need a `returnTo`.

Email and deep links:

- Existing direct detail links, highlight behavior, and confirmation/action query parameters remain supported.
- Reserved non-filter query keys are ignored by list filter parsing and are never forwarded to backend filters.

Auth redirects:

- Router guards must preserve the complete target full path, including list query state.
- An unauthenticated visit to a URL such as `/sc?status=pending&page=2&q=abc` must return to that exact list URL after login.

## Error Handling

- Query failure preserves current URL and search state.
- Query failure clears current `rows` and records `state.error`.
- Invalid pagination values in URL fall back to defaults.
- Invalid sort/direction values in URL fall back to defaults.
- Unknown filter keys in URL are ignored and removed on the next list-state URL sync.
- Backend field whitelist validation remains in place for defense in depth.
- Export errors continue to use existing message behavior.

## Testing

Backend tests:

- Add or update query service tests for fuzzy advanced text filters across PO, SC, GR, and Vendor.
- Include representative fields such as PO number, vendor name, cost center, requester name, GR description, Vendor name, KSRM code, and contact/email fields.

Frontend tests:

- If Vue-specific tests are added, introduce an explicit test harness and document the command in `frontend/package.json`.
- Vue tests should mock `callApi`, `vue-router`, and timers for debounce behavior.
- Verify `applyFilter` stores text and filters, resets to page 1, syncs URL, and queries.
- Verify `changePage` and `changePageSize` keep current text and filters.
- Verify `changeSort` sets sort/direction, resets to page 1, syncs URL, and queries.
- Verify URL query initializes list state and reflected filter-bar values.
- Verify browser back/forward query changes re-run the search.
- Verify `reset` clears search/filter query parameters.
- Verify selected rows are cleared after list state transitions.
- Verify unauthenticated auth redirects preserve list query state after login.
- Verify export payloads include `text` and omit pagination for all matching rows.

Verification commands:

- `uv run pytest tests/test_query_service.py tests/test_query_filters.py`
- Any added frontend test command from `frontend/package.json`
- `npm.cmd run build` from the `frontend` directory

## Implementation Notes

- Keep the first implementation focused on search state, URL sync, Vendor pagination, export input correctness, and fuzzy filter semantics.
- Avoid visual redesign in this iteration.
- Keep backend query whitelist explicit; do not infer arbitrary URL keys into SQL filters.
- Keep Operation Logs and Email Logs unchanged in this iteration, even though they have related list-state patterns.
