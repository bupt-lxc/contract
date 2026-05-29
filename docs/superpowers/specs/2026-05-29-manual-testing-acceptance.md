# Manual Testing Acceptance Document — SC/GR Management System

Date: 2026-05-29
Branch: `fix/core-issues`

## Environment Setup

1. Start the desktop app in dev mode: `uv run python -m sc_gr_app.main --dev`
2. Ensure the Vue frontend dev server is running: `cd frontend && npm run dev`
3. The app should auto-create a dev admin user on first launch.
4. For notification testing, start the notification script: `uv run python -m sc_gr_app.notification --draft --poll-interval 60`

## Test Data Prerequisites

Before testing, create the following test data (each step creates data for subsequent tests):

1. Create at least **2 vendors** with different service scopes
2. Create at least **3 SCs** across different statuses (draft, pending, approved)
3. Create at least **2 POs** tied to those SCs
4. Create at least **2 GRs** tied to those POs

---

## Section 1: Login & Authentication

### 1.1 — Dev-mode auto-login
- [ ] Launch app; verify it auto-creates and logs in as admin user (machine-id based)
- [ ] Verify the sidebar shows all navigation items (Workbench, SC, PO, GR, Vendor, Logs, Email, System)

### 1.2 — Login screen (non-dev)
- [ ] Verify the login screen appears when `SC_GR_DEV` is not set and machine_id is not registered
- [ ] Verify unregistered machine shows "not authorized" error

---

## Section 2: Workbench (Home)

### 2.1 — Admin workbench cards
- [ ] Verify 4 cards display: Pending SCs, Pending POs, Pending GRs, My Drafts
- [ ] Verify each card shows up to 5 rows with Status, ID, and Amount columns
- [ ] Click "View all" on any card → navigates to the corresponding list page
- [ ] Click a row in Pending SCs → navigates to SC detail
- [ ] Click a row in Pending POs → navigates to PO detail
- [ ] Click a row in Pending GRs → navigates to PO detail (parent PO page)
- [ ] Click a row in My Drafts → navigates to SC detail

### 2.2 — Non-admin workbench cards
- [ ] Create a non-admin user and log in
- [ ] Verify cards show: My Pending SCs, My Drafts, Denied SCs, Active POs
- [ ] Verify no admin-only cards appear

---

## Section 3: SC Management

### 3.1 — SC List Page (`/sc`)

#### 3.1.1 — Display
- [ ] Verify table shows SC records with columns: Status, SC No, SC ID, Requester, Type, Cost Center, Amount, Contract Period
- [ ] Verify pagination appears when rows > page size
- [ ] Verify page size change (sizes) works
- [ ] Verify page navigation (prev/pager/next/jumper) works

#### 3.1.2 — Advanced Filter Bar
- [ ] Verify text search input is always visible with placeholder "Search..."
- [ ] Type a keyword → verify results filter after 500ms debounce (searches SC No, Requester, Cost Center, Description)
- [ ] Click "Advanced Filters" to expand filter panel
- [ ] Verify all filter fields appear: Status (select), Request Type (select), Cost Center, SC ID, SC No, Requester, Created By, Service Start (date range), SC Amount (amount range)
- [ ] Filter by Status = "pending" → verify only pending SCs shown
- [ ] Filter by Status = "approved" → verify only approved SCs shown
- [ ] Filter by Status = "denied" → verify only denied SCs shown
- [ ] Filter by Status = "closed" → verify only closed SCs shown
- [ ] Filter by Request Type → verify dropdown shows: material, service, fixed_asset, FC
- [ ] Filter by SC ID (exact match) → verify correct record returned
- [ ] Filter by SC No (partial match works via text search) → verify correct records
- [ ] Filter by Requester → verify records filtered to that requester
- [ ] Filter by Created By → verify records filtered to that creator
- [ ] Filter by Service Start date range → verify records within date range
- [ ] Filter by SC Amount min-max → verify records within amount range
- [ ] Clear individual filter → verify filter removed and results update
- [ ] Click "Reset" → verify all filters clear and full list returns
- [ ] Verify table column sort (click column headers with sort icon) → verify ascending/descending order

### 3.2 — Create SC Draft (`/sc` → "New SC" button)

#### 3.2.1 — Form validation (draft mode)
- [ ] Click "New SC" button → SC form dialog opens
- [ ] Verify SC ID field is NOT present (auto-generated)
- [ ] Click "Save Draft" with all fields empty → verify only `requester_id` is required
- [ ] Fill in requester_id and click "Save Draft" → verify draft saved successfully, dialog closes
- [ ] Verify new draft SC appears in list with status "draft"

#### 3.2.2 — Form validation (submit mode)
- [ ] Click "New SC" → fill in requester_id only → click "Save & Submit" → verify validation errors for: request_type, cost_center, sc_amount, service_period_start, service_period_end
- [ ] Fill all required submit fields → click "Save & Submit" → verify SC created and in "pending" status
- [ ] Verify the SC ID is auto-generated in format `SC-{MACHINE}-{YYYYMMDD}-{SEQ:03d}`

#### 3.2.3 — Form fields
- [ ] Verify all form fields render: SC No, Requester, Request Type, Cost Center, SC Amount, Service Period Start, Service Period End, Description
- [ ] Verify required fields (submit mode) show red asterisk: Requester, Request Type, Cost Center, SC Amount, Service Period Start, Service Period End
- [ ] Verify optional fields do NOT show red asterisk: SC No, Description
- [ ] Verify SC No accepts manual input (optional external system reference)

### 3.3 — SC Detail Page (`/sc/:id`)

#### 3.3.1 — Display
- [ ] Verify SC information card shows all fields: SC ID, SC No, Status, Requester, Request Type, Cost Center, SC Amount, Service Period Start/End, Description, Created By, Created At, etc.
- [ ] Verify status badge displays correctly for each status (draft=pending/pending=pending/approved=approved/denied=denied/closed=closed)
- [ ] Verify PO Records section lists all POs under this SC
- [ ] Verify Audit section lists all audit log entries for this SC
- [ ] Verify Notification Settings card appears at bottom

#### 3.3.2 — SC Actions (status transitions)
- [ ] **Draft SC**: verify "Edit" and "Submit" buttons visible; Approve/Deny/Close hidden
- [ ] **Pending SC**: verify "Approve", "Deny" buttons visible (admin); "Close" visible
- [ ] **Approved SC**: verify "Close" button visible; Approve/Deny hidden
- [ ] **Denied SC**: verify no action buttons except possibly Edit
- [ ] **Closed SC**: verify no action buttons

#### 3.3.3 — Edit SC
- [ ] Click "Edit" on SC detail → form dialog opens pre-filled with current SC data
- [ ] Modify fields → click "Save" → verify SC updated, detail refreshes
- [ ] Verify the updated fields reflect in the detail view

#### 3.3.4 — Submit SC (draft → pending)
- [ ] On a draft SC, click "Submit" → confirmation dialog appears
- [ ] Confirm → verify SC status transitions to "pending"
- [ ] Cancel → verify no change

#### 3.3.5 — Approve SC
- [ ] On a pending SC (as admin), click "Approve" → confirmation dialog appears
- [ ] Confirm → verify SC status transitions to "approved"
- [ ] Cancel → verify no change

#### 3.3.6 — Deny SC
- [ ] On a pending SC (as admin), click "Deny" → confirmation dialog appears
- [ ] Confirm → verify SC status transitions to "denied"

#### 3.3.7 — Close SC (with confirmation text)
- [ ] On an approved SC, click "Close" → prompt asks to type "I CONFIRM CLOSE THIS SC"
- [ ] Type wrong text → verify rejected with error message
- [ ] Type exact text → verify SC status transitions to "closed"

### 3.4 — Add PO from SC Detail
- [ ] On SC detail, click "Add PO" → PO form dialog opens
- [ ] Verify PO ID field is NOT present (auto-generated)
- [ ] Fill required fields (vendor_id, po_amount) → click "Save"
- [ ] Verify PO created and appears in PO Records section
- [ ] Click on PO row → navigates to PO detail page

---

## Section 4: PO Management

### 4.1 — PO List Page (`/po`)

#### 4.1.1 — Display
- [ ] Verify table shows PO records with proper columns
- [ ] Verify pagination works

#### 4.1.2 — Advanced Filter Bar
- [ ] Verify all filter fields: Status (select: Pending/Approved/Finished), PO ID, PO No, SC ID, Vendor ID, Vendor Name, PO Amount (range), Contract From (date range), Contract To (date range)
- [ ] Filter by Status → verify correct status filter
- [ ] Filter by Vendor Name → verify correct vendor records
- [ ] Filter by PO Amount min-max → verify correct amount range
- [ ] Filter by Contract From/To date range → verify correct date range (range operators `_from`/`_to`)
- [ ] Text search → verify searches across PO No, Vendor Name, etc.
- [ ] Reset filters → verify all cleared

#### 4.1.3 — PO Table Actions
- [ ] Click a PO row → navigates to PO detail
- [ ] Click "Edit" icon on a PO row → PO edit dialog opens
- [ ] Click "Approve" on a pending PO → confirmation dialog → PO approved
- [ ] Click "Finish" on an approved PO → confirmation dialog → PO finished

### 4.2 — PO Detail Page (`/sc/:scId/po/:poId`)

#### 4.2.1 — Display
- [ ] Verify PO information card: PO ID, PO No, Vendor, PO Amount, Contract From/To, Contract No, Payment Freq
- [ ] Verify PO ID is auto-generated format `PO-{MACHINE}-{YYYYMMDD}-{SEQ:03d}`
- [ ] Verify GR Records section shows GRs tied to this PO

#### 4.2.2 — PO Actions
- [ ] Edit PO → form dialog opens pre-filled → modify → save → detail refreshes
- [ ] Approve PO (pending) → confirm → status changes to approved
- [ ] Finish PO (approved) → confirm → status changes to finished

### 4.3 — Add GR from PO Detail
- [ ] Click "Add GR" → GR form dialog opens
- [ ] Verify GR ID field is NOT present (auto-generated)
- [ ] Fill required fields (requester_id, estimated_amount) → click "Save"
- [ ] Verify GR created and appears in GR Records section

---

## Section 5: GR Management

### 5.1 — GR List Page (`/gr`)

#### 5.1.1 — Display
- [ ] Verify table shows: Status, GR ID, PO No, SC No, Vendor, Estimated Amount, Con Value
- [ ] Verify pagination works

#### 5.1.2 — Advanced Filter Bar
- [ ] Verify all filter fields: Status (select: Pending/Approved/Cancelled), GR ID, PO ID, SC ID, Requester, Vendor ID, Est. Amount (range), Con Value (range)
- [ ] Filter by Status → verify correct status filter
- [ ] Filter by SC ID → verify GRs linked to that SC
- [ ] Filter by Est. Amount range → verify correct range
- [ ] Filter by Con Value range → verify correct range
- [ ] Reset filters → verify all cleared

### 5.2 — GR Actions (from PO Detail page)

#### 5.2.1 — Edit GR
- [ ] Click "Edit" on a GR row → GR form dialog opens pre-filled
- [ ] Modify fields → save → verify GR updated

#### 5.2.2 — Approve GR (with con_value prompt)
- [ ] Click "Approve" on a pending GR → prompt appears: "Enter contract value (con_value) for this GR:"
- [ ] Enter invalid value (e.g., "abc") → verify rejected with "Enter a valid positive number"
- [ ] Enter valid value (e.g., "1500.50") → verify GR approved, con_value stored
- [ ] Cancel prompt → verify no change

#### 5.2.3 — Cancel GR
- [ ] Click "Cancel" on a GR → confirmation dialog appears
- [ ] Confirm → verify GR status changes to "cancelled"
- [ ] Cancel → verify no change

---

## Section 6: Vendor Management

### 6.1 — Vendor List Page (`/vendor`)

#### 6.1.1 — Display
- [ ] Verify table shows: Vendor Name, KSRM Code, Service Scope, Contact, Phone, Email
- [ ] Verify pagination works

#### 6.1.2 — Advanced Filter Bar
- [ ] Verify all filter fields: Vendor Name, Vendor ID, KSRM Code, Service Scope, Created By, Contact, Email
- [ ] Filter by Vendor Name → verify correct results
- [ ] Filter by Service Scope → verify correct scope
- [ ] Filter by KSRM Code → verify exact match
- [ ] Filter by Email → verify correct records
- [ ] Text search → verify searches across vendor_name, service_scope, contact_person, email, description
- [ ] Reset filters → verify all cleared

### 6.2 — Create Vendor
- [ ] Click "Add Vendor" → form dialog opens
- [ ] Verify all form fields: Vendor Name, KSRM Code, Service Scope, Contact, Phone, Email
- [ ] Fill all fields → save → verify vendor appears in list
- [ ] Submit with empty vendor_name → verify validation error

### 6.3 — Edit Vendor
- [ ] Click "Edit" on a vendor row → form dialog opens pre-filled
- [ ] Modify fields → save → verify changes reflected in list

### 6.4 — Disable Vendor
- [ ] Click "Disable" on a vendor → confirmation appears
- [ ] Confirm → verify success message "Vendor disabled"
- [ ] Cancel → verify no change

---

## Section 7: Audit Logs

### 7.1 — Audit Logs Page (`/logs`)

#### 7.1.1 — Display
- [ ] Verify table shows: Created, Action, Object, Object ID, SC ID, Operator, Machine
- [ ] Verify all audit events from SC/PO/GR/Vendor operations appear
- [ ] Verify pagination works

#### 7.1.2 — Advanced Filter Bar
- [ ] Verify all filter fields: Action, Object Type, Object ID, SC ID, Operator, Machine, Mode
- [ ] Filter by Action → verify specific action type (e.g., "approve_sc")
- [ ] Filter by Object Type → verify specific entity type (e.g., "sc", "po", "gr")
- [ ] Filter by SC ID → verify all audit entries for that SC
- [ ] Filter by Operator → verify entries by that user
- [ ] Filter by Machine → verify entries from that machine
- [ ] Text search → verify searches action_type, object_type, object_id, sc_id, operator_id, machine_id
- [ ] Reset filters → verify all cleared

---

## Section 8: Email Notification Queue

### 8.1 — Email Logs Page (`/emails`)

#### 8.1.1 — Display
- [ ] Verify table shows: Type (SC/PO/GR tag), Entity ID, Event Type (Status/Date/Amount), Event, To, CC, Status, Created, Sent, Error
- [ ] Verify Type tags render with correct colors (SC=default, PO=warning, GR=info)
- [ ] Verify Event Type tags render correctly (Status=primary, Date/Amount=warning)
- [ ] Verify Status tags: sent=success, failed=danger, pending=warning
- [ ] Verify pagination works

#### 8.1.2 — Filters
- [ ] Filter by Status → verify dropdown: Pending, Sent, Failed
- [ ] Filter by Type → verify dropdown: SC, PO, GR
- [ ] Filter by Entity ID → verify exact match
- [ ] Combine filters → verify AND logic
- [ ] Click "Refresh" → verify table reloads

---

## Section 9: System Settings

### 9.1 — Current User Display
- [ ] Verify "Current User" section shows: Machine ID, Name, Role, Email
- [ ] Verify admin role shows as red tag

### 9.2 — User Management (Admin only)
- [ ] Verify "User Management" section visible for admin
- [ ] Verify "Add User" button visible

#### 9.2.1 — Create User
- [ ] Click "Add User" → form dialog opens
- [ ] Fill Machine ID, Name, Email, Role → save → verify user appears in list
- [ ] Submit empty → verify validation errors

#### 9.2.2 — Edit User
- [ ] Click "Edit" on a user → form opens pre-filled
- [ ] Modify role/email → save → verify changes reflected

#### 9.2.3 — Disable/Enable User
- [ ] Click "Disable" on an active user → confirm → verify status changes
- [ ] Click "Enable" on a disabled user → confirm → verify status changes to active

### 9.3 — Notification Defaults (Admin only)
- [ ] Verify "Notification Defaults" section visible for admin
- [ ] Verify "Admin Recipients" multi-select → can select multiple users
- [ ] Verify "Transition Rules" section with entity type tabs/selectors
- [ ] Verify To/CC recipient toggles for each event type (status change, threshold date, threshold amount)
- [ ] Verify "Default CC" multi-select → can select multiple users
- [ ] Verify "Default Thresholds" section with date and amount thresholds
- [ ] Modify settings → click "Save" → verify "Notification defaults saved" message
- [ ] **Multi-select fix**: verify `el-select multiple` dropdowns respond to clicks and register selections (this was broken before the `:teleported="false"` fix)

### 9.4 — Per-SC Notification Config (on SC Detail page)
- [ ] Navigate to an approved SC detail
- [ ] Scroll to "Notification Settings" card
- [ ] Toggle "Enable Notifications" on/off
- [ ] Add CC recipients via multi-select → verify selections register
- [ ] Select threshold rules (date thresholds, amount thresholds)
- [ ] Click "Save" → verify "Notification settings saved" message
- [ ] **Multi-select fix**: verify `el-select multiple` works correctly in SC detail

---

## Section 10: Budget Display

### 10.1 — SC Budget
- [ ] On SC detail page, verify budget amounts display (SC Amount, Used, Remaining)
- [ ] Create a GR under this SC → verify Used/Remaining update

### 10.2 — PO Budget
- [ ] On PO detail page, verify budget amounts display
- [ ] Create a GR under this PO → verify Used/Remaining update

### 10.3 — Amount Display Component
- [ ] Verify all amount fields render with proper currency formatting
- [ ] Verify `AmountDisplay` component handles: null, 0, positive values

---

## Section 11: Navigation & Layout

### 11.1 — Sidebar Navigation
- [ ] Verify all sidebar items: Workbench, SC, PO, GR, Vendor, Audit Logs, Email, System
- [ ] Click each → verify correct page loads
- [ ] Verify active item is highlighted
- [ ] Verify branding/logo area at top

### 11.2 — Route Guard
- [ ] Access any non-login route when not authenticated → redirected to /login
- [ ] Login → redirected back to originally requested route

### 11.3 — Responsive / Window Resize
- [ ] Resize the window → verify layout adapts without breaking
- [ ] Verify tables remain scrollable on narrow windows

---

## Section 12: Auto-Generated IDs

### 12.1 — SC ID Format
- [ ] Create a new SC → verify SC ID format: `SC-{MACHINE_ID}-{YYYYMMDD}-{SEQ}`
- [ ] Create a second SC on same day → verify sequence increments (001 → 002)
- [ ] Verify SC ID is displayed in list, detail, and referenced in audit logs

### 12.2 — PO ID Format
- [ ] Create a new PO → verify PO ID format: `PO-{MACHINE_ID}-{YYYYMMDD}-{SEQ}`
- [ ] Create a second PO on same day → verify sequence increments

### 12.3 — GR ID Format
- [ ] Create a new GR → verify GR ID format: `GR-{MACHINE_ID}-{YYYYMMDD}-{SEQ}`
- [ ] Create a second GR on same day → verify sequence increments

---

## Section 13: Concurrency (if multi-user setup available)

### 13.1 — Lock Conflict
- [ ] User A opens SC detail → User B opens same SC detail
- [ ] Both edit and save → verify one succeeds, other gets lock conflict error
- [ ] Verify stale lock does not block indefinitely

---

## Section 14: Regression Checks

### 14.1 — Operations that MUST work
- [ ] Create SC draft
- [ ] Submit SC (draft → pending)
- [ ] Approve SC (pending → approved)
- [ ] Deny SC (pending → denied)
- [ ] Close SC (approved → closed)
- [ ] Create PO (from SC detail)
- [ ] Update PO
- [ ] Approve PO (pending → approved)
- [ ] Finish PO (approved → finished)
- [ ] Create GR (from PO detail)
- [ ] Update GR
- [ ] Approve GR (with con_value prompt)
- [ ] Cancel GR (pending → cancelled)
- [ ] Create Vendor
- [ ] Update Vendor
- [ ] Disable Vendor
- [ ] Create User
- [ ] Update User
- [ ] Disable/Enable User
- [ ] Save notification defaults
- [ ] Save per-SC notification config

### 14.2 — Error handling
- [ ] Verify network/bridge errors show user-friendly error messages (not raw stack traces)
- [ ] Verify ElMessage.error displays for failed operations
- [ ] Verify empty states show descriptive messages (not just blank pages)

---

## Test Results Summary

| Section | Feature | Pass/Fail | Notes |
|---|---|---|---|
| 1 | Login & Auth | | |
| 2 | Workbench | | |
| 3 | SC Management | | |
| 4 | PO Management | | |
| 5 | GR Management | | |
| 6 | Vendor Management | | |
| 7 | Audit Logs | | |
| 8 | Email Queue | | |
| 9 | System Settings | | |
| 10 | Budget Display | | |
| 11 | Navigation | | |
| 12 | Auto-Generated IDs | | |
| 13 | Concurrency | | |
| 14 | Regression | | |

---

## Known Limitations

1. **Parallel subagent dispatch**: Multiple users creating SCs simultaneously with the same machine ID will get sequential IDs — the second writer waits for the first's lock to release before generating an ID.
2. **Date range filters**: Filter by `service_period_start` date uses the `_from`/`_to` range operators to filter records with start date >= from and <= to.
3. **Text search**: Searches only `text_columns` defined in `query_service.py`, not all columns.
4. **Notification queue**: Only shows entries; actual email sending requires the standalone notification script running on a machine with Outlook.
