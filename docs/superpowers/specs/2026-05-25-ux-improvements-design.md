# UX Improvements Design

**Date:** 2026-05-25
**Status:** Approved

## Overview

Seven UX improvements for the SC management desktop app, implemented incrementally using PicoCSS v2 + Alpine.js v3 alongside the existing vanilla JS architecture.

## Technology Stack (Post-Migration)

- **PicoCSS v2** (~30KB CSS) — replaces most of `styles.css` design tokens. Handles typography, spacing, forms, buttons, tables, modals.
- **Alpine.js v3** (~15KB) — declarative interactivity: modal toggles, tree expand/collapse, form bindings. Loaded via CDN `<script>` in `index.html`.
- **Existing vanilla JS** — `app.js`, `state.js`, `views.js` remain as orchestrator and renderers. Alpine directives are embedded in `innerHTML` strings.
- **`styles.css`** — reduced to app-specific layout rules only (side-nav, drawer, toolbar grid).

## Implementation Strategy

**Incremental migration (Approach 1):** Each improvement implemented and verified independently. App stays functional throughout. Order:

1. Add PicoCSS + Alpine.js CDN links, strip redundant CSS
2. Login screen (gates all access)
3. Close confirmation modal
4. GR nesting under PO (tree layout)
5. PO/GR status badges with colored left border
6. Form scroll behavior (overflow-x: auto + sticky buttons)
7. Vendor selection as `<select>` dropdown in PO form

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

## Files Affected

| File | Change |
|------|--------|
| `sc_gr_app/web/index.html` | Add PicoCSS + Alpine CDN links |
| `sc_gr_app/web/styles.css` | Strip redundant tokens; add: danger button variant, status-row borders, section-toolbar, scroll fixes, login screen styles, modal styles |
| `sc_gr_app/web/app.js` | Login gate in startup flow; close modal state management; vendor list fetch for PO forms |
| `sc_gr_app/web/components/views.js` | New: `renderLoginScreen()`, `renderCloseModal()`. Refactored: `renderPoSection()` (tree layout + nested GRs), `renderPoForm()` (vendor select), `renderGrForm()` (po_id pre-fill). Removed: standalone `renderGrSection()` |
| `sc_gr_app/web/components/state.js` | Add `confirmingClose` to `scDetail`; add `vendors[]` to `scDetail` |
| `sc_gr_app/web/components/tables.js` | Minor: status column as first column in Pico tables |
| `sc_gr_app/api/bridge.py` | No changes (existing API surface is sufficient) |

## Files NOT Affected

- `sc_gr_app/services/*` — no backend logic changes
- `sc_gr_app/db/*` — no schema changes
- `sc_gr_app/web/components/auth.js` — login gate replaces its role; may be deprecated
- `sc_gr_app/web/components/format.js` — no changes
- `sc_gr_app/web/components/api.js` — no changes

## Testing

- Existing pytest suite must continue passing (no backend changes)
- Manual verification of each improvement in the desktop app
- Key scenarios:
  1. Startup with authorized machine ID → login screen → enter → main app
  2. Startup with unauthorized machine ID → login screen shows error
  3. Close SC → modal appears → type confirmation → SC closes
  4. Close SC → modal appears → wrong text → button stays disabled
  5. Expand PO → GR children visible; collapse → hidden
  6. Long form → horizontal scroll works; action buttons stay visible
  7. Create PO → vendor dropdown populated from system vendors
