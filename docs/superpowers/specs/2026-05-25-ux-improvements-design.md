# UX Improvements Design

**Date:** 2026-05-25
**Status:** Approved

## Overview

Eight UX improvements plus seed data for the SC management desktop app, implemented incrementally using PicoCSS v2 + Alpine.js v3 alongside the existing vanilla JS architecture.

## Technology Stack (Post-Migration)

- **PicoCSS v2** (~30KB CSS) — replaces most of `styles.css` design tokens. Handles typography, spacing, forms, buttons, tables, modals.
- **Alpine.js v3** (~15KB) — declarative interactivity: modal toggles, tree expand/collapse, form bindings. Loaded via CDN `<script>` in `index.html`.
- **Existing vanilla JS** — `app.js`, `state.js`, `views.js` remain as orchestrator and renderers. Alpine directives are embedded in `innerHTML` strings.
- **`styles.css`** — reduced to app-specific layout rules only (side-nav, drawer, toolbar grid).

## Implementation Strategy

**Incremental migration (Approach 1):** Each improvement implemented and verified independently. App stays functional throughout. Order:

1. Expand seed users to six named individuals (two admins, four requesters)
2. Add PicoCSS + Alpine.js CDN links, strip redundant CSS
3. Login screen (gates all access)
4. Close confirmation modal
5. GR nesting under PO (tree layout)
6. PO/GR status badges with colored left border
7. Form scroll behavior (overflow-x: auto + sticky buttons)
8. Vendor selection as `<select>` dropdown in PO form
9. Requester selection as `<select>` dropdown in SC form
10. User management in System view (admin-only CRUD)

---

## 1. Login Screen

**Purpose:** Replace the current "route to System view showing Unauthorized error" flow with a proper login gate.

**Flow:**
```
App start → renderLoginScreen() → call current_user()
  ├─ Loading: spinner + "Verifying identity..."
  ├─ Authorized: "Welcome, [Name] ([Role])" + "Enter System" button
  └─ Unauthorized: machine ID shown, "not authorized, contact admin" message
```

**Layout:**
- Full-screen neutral background (Pico body default)
- Centered card (`max-width: 400px`, Pico `.container`)
- App title at top
- Three states managed by Alpine `x-show`
- On "Enter System" click → discard login DOM → render normal shell (nav + toolbar + content)

**Identity model:** Unchanged — machine-ID based, no passwords. The login screen is a UX gate only.

---

## 2. Close Confirmation Modal

**Purpose:** Replace `window.confirm()` with a custom modal requiring explicit text confirmation.

**Trigger:** Red danger button (Pico secondary + custom red variant).

**Modal (Alpine `x-show`):**
- Backdrop overlay, `z-index: 100`
- Card with:
  - Title: "Close SC [SC No.]?"
  - Warning: "This SC will be permanently closed. No further PO or GR operations will be possible. This action cannot be undone."
  - `<input>` bound via `x-model="confirmationText"`
  - Red "Close SC" button, `:disabled="confirmationText !== 'I CONFIRM CLOSE THIS SC'"`
  - Gray "Cancel" button → closes modal

**Integration:** Replaces `window.confirm()` in `app.js` → `handleScAction` close case. Modal rendered inline in SC detail view when `state.scDetail.confirmingClose` is true. On confirm, calls existing `resolveScAction("close", ...)`.

---

## 3. GR Nesting Under PO (Tree Layout)

**Purpose:** GRs display as children of their parent PO instead of in a separate section. Reflects the many-GR-to-one-PO relationship.

**Layout per PO row group:**
```
[▶] PO-001 | Vendor A | ¥50,000 | [status] | [actions]
     ├─ GR-101 | pending | ¥10,000 | [actions]
     └─ GR-102 | approved | ¥8,000 | [actions]
```

**Alpine mechanics:**
- Each PO row group: `x-data="{ expanded: false }"`
- Click PO row → `@click="expanded = !expanded"`
- GR rows: `x-show="expanded"` with left-padding indent
- Chevron: `▶` ↔ `▼` on expand/collapse

**GR form:**
- "Add GR" button per PO (inside expanded area)
- `po_id` pre-fills from parent PO — no manual selection needed
- Each PO header shows GR count badge

**Removal:** Standalone `.gr-section` removed entirely.

---

## 4. PO/GR Status Badges

**Purpose:** Consistent status styling with main SC list, moved to leftmost column for quick scanning.

**Style:** Same `.status-badge` pill component (12px bold, 999px border-radius, colored background).

**Row left border (4px):**
```css
.status-row.status-approved  { border-left: 4px solid var(--success); }
.status-row.status-pending   { border-left: 4px solid var(--warning); }
.status-row.status-cancelled { border-left: 4px solid var(--danger); }
```

**Column order (PO):** Status → PO No → Vendor → Amount → Open Amount → Contract From → Contract To → Actions

**Column order (GR):** Status → GR ID → Requester → Est. Amount → Con Value → Remark → Created → Actions

---

## 5. Form Scroll Behavior

**Problem:** `.detail-section` uses `overflow: hidden`, clipping long forms/tables. Action buttons get pushed off-screen.

**Solution:**
- `.detail-section`: `overflow-x: auto` (replaces `overflow: hidden`)
- New `.section-toolbar`: `display: flex; justify-content: space-between; position: sticky; top: 0` — title left, buttons right
- Action buttons: `flex-shrink: 0` — never collapse
- Form grid and tables scroll horizontally within the section card when viewport is too narrow
- PicoCSS tables wrapped for horizontal scroll

---

## 6. Vendor Selection in PO Form

**Purpose:** Replace manual vendor_id text input with a dropdown of existing vendors.

**Data:** `search_vendors({ limit: 500 })` called once on SC detail entry. Results cached in state.

**Template:**
```html
<select name="vendor_id" required>
  <option value="">-- Select Vendor --</option>
  <option value="V001">ABC Supplies — KSRM: 1234 — Maintenance</option>
</select>
```

**Edge case:** Empty vendor list → show "No vendors available. Add vendors in Vendor Management first." Validate non-empty selection on submit.

---

## 7. Requester Selection in SC Form

**Purpose:** Replace manual `requester_id` text input in SC create/edit forms with a dropdown of active users.

**Data:** All active users (`role IN ('admin', 'requester')` and `status = 'active'`) fetched once at app startup, cached in `state.users`.

**Template (same pattern as vendor select):**
```html
<select name="requester_id" required>
  <option value="">-- Select Requester --</option>
  <option value="V2SE7PP">Li, Xingchen (C/EV-L) — V2SE7PP</option>
  <option value="UJWVFIH">Su, Tong (C/EV-L) — UJWVFIH</option>
  ...
</select>
```

**Affects:** `renderScCreateForm()` and `renderScEditForm()` — replace `<input name="requester_id">` with `<select>`.

---

## 8. User Management in System View

**Purpose:** Allow admins to add, edit, and disable users directly from the System view.

**Visibility:** Only users with `role === "admin"` see the management section. Requesters see only the metric cards.

**User table columns:** Machine ID → Name → Email → Role → Status → Actions

**Operations:**

| Action | Behavior |
|--------|----------|
| Add | Inline form with: machine_id (7-digit, validated), user_name, email, role (`admin`/`requester` select). `user_id` auto-generated as `U-{machine_id}`. `status` defaults to `active`. |
| Edit | Inline form for user_name, email, role. `machine_id` is read-only once set. |
| Disable | Sets `status = 'disabled'` (soft delete — preserves FK integrity). Confirm dialog before proceeding. |

**Audit logging:** All three operations write to `audit_logs` via existing `audit_service.write_audit_log()`.

**Backend (new):**
- `user_service.py`: `create_user()`, `update_user()`, `disable_user()`
- `bridge.py`: `create_user`, `update_user`, `disable_user` endpoints — require admin role check

**Locking:** No lease lock needed — user management is independent of SC/PO/GR records.

---

## 9. Seed Users

**Purpose:** Replace the single `seed_default_admin()` with a function that seeds all six initial users on first startup.

**User IDs:** Auto-generated as `U-{machine_id}`.

**Seeded users:**

| Name | Email | Machine ID | Role |
|------|-------|------------|------|
| Li, Xingchen (C/EV-L) | xingchen.li@audi.com.cn | V2SE7PP | requester |
| Su, Tong (C/EV-L) | tong.su@audi.com.cn | UJWVFIH | requester |
| Yang, Qiaomin (C/EV-L) | qiaomin.yang@audi.com.cn | EYANQM0 | admin |
| Ye, Xiaorui (C/EV-L) | xiaorui.ye@audi.com.cn | FO5LZ6P | requester |
| Zhou, Liwei (C/EV-L) | liwei.zhou@audi.com.cn | EZHOLW0 | requester |
| Sun, Jialing (C/EV-L) | jialing.sun@audi.com.cn | FPBTMS5 | admin |

**Idempotency:** Each user only inserted if their `machine_id` doesn't already exist. Safe to run on every startup.

**Existing data safety:** Users already in the database (including the current default admin `U-ADMIN`) are left untouched — the seed only fills gaps.

---

## Files Affected

| File | Change |
|------|--------|
| `sc_gr_app/web/index.html` | Add PicoCSS + Alpine CDN links |
| `sc_gr_app/web/styles.css` | Strip redundant tokens; add: danger button variant, status-row borders, section-toolbar, scroll fixes, login screen styles, modal styles, user management styles |
| `sc_gr_app/web/app.js` | Login gate in startup flow; close modal state management; vendor + user list fetch for forms |
| `sc_gr_app/web/components/views.js` | New: `renderLoginScreen()`, `renderCloseModal()`, `renderUserManagement()`. Refactored: `renderPoSection()` (tree layout + nested GRs), `renderPoForm()` (vendor select), `renderScCreateForm()` (requester select), `renderScEditForm()` (requester select), `renderGrForm()` (po_id pre-fill). Expanded: `renderSystem()` (user management section). Removed: standalone `renderGrSection()` |
| `sc_gr_app/web/components/state.js` | Add `confirmingClose`, `vendors[]`, `users[]` to state |
| `sc_gr_app/web/components/tables.js` | Minor: status column as first column |
| `sc_gr_app/services/user_service.py` | New: `create_user()`, `update_user()`, `disable_user()`. Refactored: `seed_default_admin()` → `seed_users()` with six initial users |
| `sc_gr_app/api/bridge.py` | New endpoints: `create_user`, `update_user`, `disable_user` (admin-only). Existing endpoints: no changes |

## Files NOT Affected

- `sc_gr_app/db/*` — no schema changes
- `sc_gr_app/web/components/auth.js` — login gate replaces its role; may be deprecated
- `sc_gr_app/web/components/format.js` — no changes
- `sc_gr_app/web/components/api.js` — no changes
- `sc_gr_app/services/sc_service.py` — no changes (requester dropdown is frontend-only)
- `sc_gr_app/services/po_service.py` — no changes
- `sc_gr_app/services/gr_service.py` — no changes

## Testing

- Existing pytest suite must continue passing
- New unit tests for `create_user()`, `update_user()`, `disable_user()` in `tests/test_user_service.py`
- New unit tests for `seed_users()` idempotency
- Manual verification of each improvement in the desktop app
- Key scenarios:
  1. Startup with authorized machine ID → login screen → enter → main app
  2. Startup with unauthorized machine ID → login screen shows error
  3. Close SC → modal appears → type confirmation → SC closes
  4. Close SC → modal appears → wrong text → button stays disabled
  5. Expand PO → GR children visible; collapse → hidden
  6. Long form → horizontal scroll works; action buttons stay visible
  7. Create PO → vendor dropdown populated from system vendors
  8. Create SC → requester dropdown populated from active users
  9. Admin: add/edit/disable user in System view → audit log recorded
  10. Non-admin: System view shows only metric cards, no user management
  11. Seed users created on first startup; idempotent on subsequent startups
