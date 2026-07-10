# PO Annual Report Export Design

## Goal

Add an admin-only annual report export button to the PO List page. The report exports annual-report rows selected by SC/PO inclusion rules, in the standard annual-report layout represented by `docs/2025 C_EG-V GR_25.09.25_update.xlsx`, excluding the template total row.

The GR annual report export already has the intended UI pattern, but the current worktree has a broken backend gap: `GrListView.vue` calls `get_gr_annual_report`, while the backend service/API methods are missing. This work will also repair that GR path so the copied pattern is usable.

## User-Facing Behavior

On PO List, admins see an annual-report export button near the existing export controls. Non-admin users do not see the button.

Clicking the button opens a compact year-picker dialog, matching the GR annual report interaction. The selected year defaults to the current year. Confirming the dialog generates an Excel file named like `PO_Annual_Report_2025.xlsx`.

The export is intentionally broader than "POs with GR this year" but narrower than "all finished POs". It includes qualifying PO rows plus SC-only rows for approved SCs that have no qualifying PO row.

## Data Scope

The backend produces one row per qualifying PO when any of these conditions is true:

1. The PO belongs to an SC whose status is `approved`, and the PO status is `active` or `finished`.
2. The PO has at least one approved/finished GR whose report year equals the selected year.
3. The PO status is currently `active`.
4. The PO status is `finished` and `pos.finished_at` is in the selected year.

This means historical finished POs are not included just because they are finished. A historical finished PO still appears if it belongs to an approved SC or has selected-year GR activity.

Draft POs under approved SCs do not enter the report through condition 1.

Independent FC POs do not have a parent SC, so they enter the report through conditions 2, 3, or 4.

The backend also produces one SC-only row for each approved SC that has no qualifying PO row. SC-only rows represent the approved SC itself, not any child PO. For SC-only rows, `PO number`, `PO amount`, previous-year GR, selected-year GR, provision, to-be-GR, FC GR, and `Remark` are blank. `Requester`, `SC no`, `Short Text`, and `SC amount` are filled from the SC.

## Report Columns

The exported workbook has one sheet with these columns:

1. `Requester`
2. `SC no`
3. `PO number`
4. `Short Text`
5. `SC amount`
6. `PO amount`
7. `{previousYear} GR`
8. `{previousYear} Provision`
9. `{selectedYear} GR`
10. `{selectedYear} to be GR`
11. `{selectedYear} FC GR`
12. `Remark`

For example, if the user selects 2025, the dynamic columns are `2024 GR`, `2024 Provision`, `2025 GR`, `2025 to be GR`, and `2025 FC GR`.

The following columns are intentionally left blank for every row:

- `{previousYear} Provision`
- `{selectedYear} to be GR`
- `{selectedYear} FC GR`
- `Remark`

`{selectedYear} FC GR` is a business formula outside this export's current scope. Its manual meaning is `{selectedYear} to be GR + {selectedYear} GR - {previousYear} Provision`; because both provision and to-be-GR are intentionally blank in this export, the FC GR column is also intentionally blank rather than calculated.

## Data Mapping

For PO rows, `Requester` comes from the PO requester user name. If the PO is SC-linked and its requester is inherited from the SC, the existing PO requester field is still used.

For SC-only rows, `Requester` comes from the SC requester user name.

For PO rows, `SC no` and `SC amount` come from the linked SC. Independent FC POs have no linked SC, so these fields are blank.

For SC-only rows, `SC no` and `SC amount` come from the SC.

`Short Text` comes from `sc_records.description`. If the row has no linked SC or the SC description is empty, `Short Text` is blank.

`PO number` comes from `pos.po_no`.

`PO amount` comes from `pos.po_amount`.

For PO rows, `{previousYear} GR` is the sum of approved/finished GR `con_value` under that PO whose report year equals the previous year.

For PO rows, `{selectedYear} GR` is the sum of approved/finished GR `con_value` under that PO whose report year equals the selected year.

For SC-only rows, both GR amount columns are blank.

The GR report year follows the existing GR annual-report intent:

- `finished` GRs use `finished_at`.
- `approved` GRs use `approved_date`.
- GRs without the relevant date are not counted in yearly totals.

Only GR statuses `approved` and `finished` are included in any annual GR totals. Draft, manager-confirm, pending, and denied GRs are excluded.

## Architecture

Backend adds `po_service.get_annual_report_data(config, year, current_user)`.

The service validates that `year` is a four-digit string, requires admin access, applies the Data Scope OR conditions, and returns rows already shaped for report export. The query joins PO, SC, user, and aggregated GR totals so the frontend does not implement financial logic.

The PO annual report query must use `LEFT JOIN sc_records` so independent FC POs are not dropped, and it must aggregate GR totals by `po_id` without requiring `pos.sc_id`.

The PO annual report backend row contract uses stable keys:

- `row_type`, with value `po` or `sc`
- `requester`
- `sc_no`
- `po_no`
- `short_text`
- `sc_amount`
- `po_amount`
- `previous_year_gr`
- `previous_year_provision`
- `selected_year_gr`
- `selected_year_to_be_gr`
- `selected_year_fc_gr`
- `remark`

The blank columns return empty strings for `previous_year_provision`, `selected_year_to_be_gr`, `selected_year_fc_gr`, and `remark`. SC-only rows also return empty strings for `po_no`, `po_amount`, `previous_year_gr`, and `selected_year_gr`.

Backend adds `ApiBridge.get_po_annual_report(payload)` beside the existing export endpoints. It defaults to the current year when omitted, calls the PO service, formats timestamps through existing helpers where relevant, and returns `{ rows }`.

Frontend updates `PoListView.vue` with:

- Admin-only annual report button, implemented with the same `isAdmin` role source pattern used by GR List.
- Year picker dialog matching the GR List pattern.
- `handleAnnualExport` that calls `get_po_annual_report`, builds dynamic year labels, and uses `useExport().exportRows`.

Frontend i18n adds PO annual-report keys to zh-CN and en-US. Existing GR i18n keys are reused only for GR.

PO annual report export does not use `ExportDialog`, `export_pos_cascade`, `build_cascade_rows`, or `compute_statistics`. It produces exactly one annual-report sheet from `get_po_annual_report(...).rows`; no overview, financial, budget-health, processing-time, requester-statistics, cascade PO/GR, selected-row, filtered-row, or CSV behavior is included.

Annual report APIs are read-only database operations. Apart from the frontend `save_file` call that writes the selected workbook path, PO/GR annual report export must not insert, update, or delete `operation_records`, `notification_queue`, `notification_config`, `notification_custom_schedule`, notification-related `app_settings` keys, or `attachments`; must not call notification/email draft helpers; and must not resolve or include attachment paths.

`useExport().exportRows`, `exportMultiSheet`, and `exportCSV` must return the `save_file` result. `exportRows` and `exportMultiSheet` must create headers from `columns` even when `rows.length === 0`. PO/GR annual report handlers must skip success toast and keep the dialog open when `result.cancelled === true`.

## GR Annual Report Repair

The current GR List UI already has:

- Annual report button that is currently visible without the backend route needed to make it work.
- Year picker dialog.
- `handleAnnualExport` calling `get_gr_annual_report`.

Because the backend method is absent in the current worktree, this feature would fail at runtime. Implementation will add or restore:

- `gr_service.get_annual_report_data(config, year, current_user)`
- `ApiBridge.get_gr_annual_report(payload)`
- Admin-only visibility for the GR annual report button, matching the PO annual-report permission rule and implemented as `v-if="isAdmin"` in the template.

The GR export column shape remains the existing one unless tests reveal a runtime issue unrelated to the missing backend route.

## Error Handling

Invalid years return a validation error from the backend.

Non-admin callers receive a permission error even if they invoke the bridge method directly.

Empty result sets still export an Excel workbook with headers.

Save dialog cancellation is treated as a no-op and does not show a success toast.

## Testing

Backend tests cover:

- PO annual report rejects invalid years.
- Non-admin users cannot fetch PO annual report data.
- Active/finished POs under approved SCs are included even when selected-year GR is empty.
- Draft POs under approved SCs are not included by the approved-SC rule.
- Approved SCs with no qualifying PO rows produce SC-only rows.
- SC-only rows leave PO and GR amount fields blank while keeping SC/requester fields.
- POs with selected-year GRs are included even when their parent SC is not approved.
- Active POs are included.
- Finished POs are included only when finished in the selected year, unless included by another rule.
- Historical finished POs are excluded when they do not match any other inclusion condition.
- Previous-year and selected-year GR totals include only approved/finished GRs.
- FC GR is intentionally blank for every row.
- Blank columns are present in the returned row shape.

GR tests cover:

- `get_gr_annual_report` backend path exists and returns approved/finished GR rows for a selected year.
- Invalid years are rejected.
- Non-admin access is rejected if the UI is made admin-only.

Frontend verification covers:

- PO and GR annual report buttons are visible only for admins.
- Year dialogs open with the current year.
- Export calls the correct bridge method and builds dynamic year headers.

## Scope Boundaries

This work does not attempt to preserve the exact template workbook styling. It follows the column order and data semantics of the standard file while using the existing SheetJS export path.

This work does not import or modify `docs/2025 C_EG-V GR_25.09.25_update.xlsx`; the file is used only as the format reference.
