# Frontend Vue Refactor Design

## Overview

Complete frontend rewrite from vanilla JS/PicoCSS/Alpine.js to Vue 3 + Element Plus. The desktop app retains its pywebview shell and JS Bridge communication model (`window.pywebview.api`), with the Vue SPA built independently and output to the existing `sc_gr_app/web/` directory.

### Design Direction: Precision Dashboard (工业精密风)

Inspired by German industrial design principles — precise, efficient, minimal decoration. Clean lines, structured grids, high information density with clear visual hierarchy. Form follows function.

- **Color**: Slate-blue primary (`#3B5998`), cool-gray backgrounds, amber as operation accent; semantic status colors (green/red/orange/blue for tags)
- **Typography**: System native fonts (Segoe UI / Aptos) for desktop-native feel. Tabular numbers for all amount columns.
- **Spatial**: Dense but ordered. 4px base radius (sharp). Subtle grid lines. Status rows with 3px left color bar.
- **Icon**: `@element-plus/icons-vue` for standard actions, custom PNG icons for domain-specific concepts if needed.

---

## Dependencies

### npm (frontend/)

```json
{
  "dependencies": {
    "vue": "^3.5",
    "vue-router": "^4.5",
    "element-plus": "^2.11",
    "@element-plus/icons-vue": "^2.3"
  },
  "devDependencies": {
    "vite": "^6.0",
    "@vitejs/plugin-vue": "^5.2"
  }
}
```

### pip (Python)

```
pystray          # System tray icon (new dependency)
Pillow           # Tray icon image handling (pystray dependency)
```

### Runtime

- **WebView2 Runtime**: Required by pywebview EdgeChromium backend. Ships with Windows 11. For Windows 10, install the Evergreen bootstrapper.

---

## Architecture

```
frontend/                          # New independent frontend project
  package.json                     # Vue 3.5 + Element Plus 2.11 + Vite 7
  vite.config.js
  index.html
  src/
    main.js                        # createApp + ElementPlus + Router
    App.vue                        # Root layout or login (conditional)
    assets/
      main.css                     # Global styles, CSS variable overrides
    api/
      bridge.js                    # Thin wrapper over window.pywebview.api
    composables/
      useSc.js                     # SC state + CRUD
      usePo.js                     # PO state + CRUD
      useGr.js                     # GR state + CRUD
      useVendor.js                 # Vendor state + CRUD
      useLogs.js                   # Audit logs state
      useUser.js                   # Current user + user list
    router/
      index.js                     # createWebHashHistory, 9+2 routes
    components/
      layout/
        SideNav.vue                # Collapsible sidebar + el-menu
        AppHeader.vue              # Title, breadcrumb, user panel
      sc/
        ScTable.vue                # SC list table
        ScFormDialog.vue           # SC create/edit dialog
        ScDetailCard.vue           # SC info el-descriptions
      po/
        PoTable.vue                # PO list table
        PoFormDialog.vue           # PO create/edit dialog
        GrTable.vue                # GR list table (in PO detail)
        GrFormDialog.vue           # GR create/edit dialog
      vendor/
        VendorFormDialog.vue
      common/
        StatusBadge.vue            # el-tag wrapper with status mapping
        AmountDisplay.vue          # Tabular-nums right-aligned amount
        FilterBar.vue              # Per-view search/filter area
      system/
        UserFormDialog.vue         # User create/edit dialog
    views/
        LoginView.vue              # Centered card, 3 states
        HomeView.vue               # Workbench dashboard
        ScListView.vue             # SC list + filters
        ScDetailView.vue           # SC detail → PO list → PO detail
        PoDetailView.vue           # PO detail → GR table
        PoListView.vue             # Global PO list
        GrListView.vue             # Global GR list
        VendorListView.vue         # Vendor list + filters
        LogsView.vue               # Audit log list + filters
        SystemView.vue             # System info + user management
```

**Build output**: `vite build` → `sc_gr_app/web/` (overwrites current static files).

**Vite config key points**:
- `base: "./"` — relative paths for file:// loading
- `build.outDir` → `../sc_gr_app/web`
- `build.emptyOutDir: true` — clean output directory
- `server.port: 5173` — dev server for development

**Development workflow**:
- `npm run dev` → Vite dev server on localhost:5173
- During dev, pywebview loads `http://localhost:5173` instead of file path
- Production: build to `sc_gr_app/web/`, load via file://

**Current web/ files to be removed** (replaced by Vite output):
- `index.html`, `app.js`, `styles.css`
- `components/` (api.js, auth.js, state.js, views.js, tables.js, forms.js, format.js)
- `icons/` — keep PNG icons, used by Vue components

---

## Routing

Uses `createWebHashHistory` (file:// protocol, no server fallback).

| Route | View | Nav Visible | Notes |
|-------|------|:--:|-------|
| `/login` | LoginView | No | Standalone layout, no sidebar/header |
| `/workbench` | HomeView | Yes | Default after login |
| `/sc` | ScListView | Yes | SC list, search, filters, New SC dialog |
| `/sc/:id` | ScDetailView | Yes | SC info + PO table, breadcrumb back to /sc |
| `/sc/:scId/po/:poId` | PoDetailView | Yes | PO info + GR table, breadcrumb back |
| `/po` | PoListView | Yes | Global PO list |
| `/gr` | GrListView | Yes | Global GR list |
| `/vendor` | VendorListView | Yes | Vendor list, search, filters |
| `/logs` | LogsView | Yes | Audit log list |
| `/system` | SystemView | Yes | Admin only |

SC detail and PO detail are NOT in the sidebar — reached via table row clicks, returned via breadcrumb.

---

## Layout Structure

```
┌──────────────┬───────────────────────────────────────────┐
│  Sidebar     │  Header (56px)                             │
│  (210px)     │  [App Title]    / SC List    [User ▼]     │
│              ├───────────────────────────────────────────┤
│  ⏿ Workbench│  Main Content                              │
│  ⏿ SC       │  ┌─ Filter/Button Bar ─────────────────┐  │
│  ⏿ PO       │  │ [Filter] [Filter] [Reset]  [+ New]  │  │
│  ⏿ GR       │  └─────────────────────────────────────┘  │
│  ⏿ Vendor   │  ┌─ el-table ──────────────────────────┐  │
│  ⏿ Logs     │  │ data rows...                         │  │
│  ⏿ System   │  └─────────────────────────────────────┘  │
│              │  ┌─ el-pagination ─────────────────────┐  │
│  ◀ Collapse │  └─────────────────────────────────────┘  │
└──────────────┴───────────────────────────────────────────┘
```

- Sidebar: `el-menu` with `router` mode, `collapse` toggle at bottom
- Header: left = title + breadcrumb, right = user name + role + logout
- Main: per-view search bar + table/detail content
- No global search in header — each view manages its own search/filter

---

## Login Page

Standalone layout (`/login`), no sidebar/header. Centered card with:

1. **Loading state**: el-skeleton with animated shimmer, "Detecting identity..."
2. **Authorized state**: user name + role displayed, green check icon, "Enter" button (→ `/workbench`)
3. **Unauthorized state**: machine ID shown, red alert icon, "Retry" button, message: "This machine is not authorized. Contact admin."

Flow: on mount → `current_user` API → branch to authorized/unauthorized. User clicks "Enter" → hide login, show main layout.

---

## Workbench (`/workbench`)

Dashboard showing actionable items, role-dependent:

**Admin view**:
| Card | Content | Action |
|------|---------|--------|
| Pending SCs | 3-5 rows, newest first | Click → sc detail |
| Pending POs | 3-5 rows, newest first | Click → po detail |
| Pending GRs | 3-5 rows, newest first | Click → po detail |
| My Drafts | Draft SCs created by me | Click → edit dialog |

**Requester view**:
| Card | Content | Action |
|------|---------|--------|
| My Pending SCs | Own SCs pending approval | Click → sc detail |
| My Drafts | Own draft SCs | Click → edit dialog |
| Denied SCs | Own denied SCs | Click → sc detail |
| Active POs | PO list under own SCs | Click → po detail |

Layout: 2x2 grid of `el-card`, each containing a compact `el-table` (3-5 rows, no pagination) and a "View all →" link.

---

## Views: Data Display

### Common Pattern for List Views (SC, PO, GR, Vendor, Logs)

Each list view has:
1. **Filter bar** at top: `el-select`(s) for enum filters + `el-input` for text search + `el-date-picker` for date filters + Reset button + New/Create button on the right
2. **el-table**: `stripe`, `border`, `v-loading` bound to composable loading state, `@sort-change` for server-side sort
3. **el-pagination** at bottom: `layout="total, sizes, prev, pager, next"`
4. **el-empty** when no data
5. **el-skeleton** for initial page load

### Status Display

`StatusBadge.vue` maps status strings to `el-tag` types:
- `pending` / `po_pending` → `warning`
- `approved` / `po_approved` → `success`
- `denied` / `cancelled` → `danger`
- `closed` / `finished` → `info`
- `draft` → `` (plain, no type)

### Amount Display

`AmountDisplay.vue` renders with `font-variant-numeric: tabular-nums`, right-aligned. Thousand-separated, 2 decimal places.

---

## SC List → Detail Flow

### SC List (`/sc`)

- Filter: status, request_type, cost_center (text)
- Table: status tag, SC No, Requester, Type, Cost Center, SC Amount, Created, Actions
- New SC button → opens `ScFormDialog` (el-dialog, 640px)
- Row click → navigates to `/sc/:id`

### SC Detail (`/sc/:id`)

- Header: SC No + status tag + action buttons (Edit, Submit, Approve, Deny, Close)
- `el-descriptions` (2-column): SC fields
- PO table (compact, no expand): PO No, Vendor, Amount, Open/Con, Status, Contract To, Actions
- Click PO row → navigate to `/sc/:scId/po/:poId`
- Add PO button → `PoFormDialog`
- Audit log table at bottom

### PO Detail (`/sc/:scId/po/:poId`)

- Breadcrumb: SC List > SC-detail > PO-detail
- Header: PO No + status tag + action buttons (Edit, Approve, Finish)
- `el-descriptions`: PO fields
- GR table (main body): GR ID, Requester, Estimated, Con Value, Status, Remark, Actions
- Add GR button → `GrFormDialog`
- Each GR row: Edit / Approve / Cancel buttons with `el-popconfirm` for destructive actions

---

## Forms: All Dialogs

All create/edit operations use `el-dialog` + `el-form`. No inline page forms.

| Dialog | Trigger | Width | Fields |
|--------|---------|-------|--------|
| ScFormDialog | SC List "New SC" / SC Detail "Edit" | 640px | sc_id, sc_no, requester (select), request_type, cost_center, sc_amount, service_period (start/end), description |
| PoFormDialog | SC Detail "Add PO" / PO Detail "Edit" | 520px | po_id, vendor (select+filterable), po_no, po_amount, contract_from/to, contract_no, payment_frequency |
| GrFormDialog | PO Detail "Add GR" / row "Edit" | 520px | gr_id, requester_id, estimated_amount, con_value, remark |
| VendorFormDialog | Vendor List "Add Vendor" / row "Edit" | 520px | vendor_id, vendor_name*, service_scope*, ksrm_vendor_code, contact_person, phone, email, description, inquiry_history |
| UserFormDialog | System page "Add User" / row "Edit" | 480px | machine_id (readonly for edit), user_name*, email, role* |

- All use `label-position="top"` for compact vertical layout
- SC create uses `el-row`/`el-col` 2-column grid for dense fields
- Validation via `el-form` `:rules`
- Save → composable method → refresh parent data → close dialog
- Cancel / close backdrop → dialog closes, no side effects

---

## Confirmation & Feedback

| Action | Component | Notes |
|--------|-----------|-------|
| Approve SC/PO/GR | `ElMessageBox.confirm` | "Approve this item?" |
| Deny SC | `ElMessageBox.confirm` | "Deny this SC?" + optional reason |
| Close SC | `ElMessageBox.prompt` | Text input: "I CONFIRM CLOSE THIS SC" |
| Cancel GR | `ElMessageBox.confirm` | "Cancel this GR?" |
| Disable Vendor/User | `el-popconfirm` on button | "Disable this item?" |
| Operation success | `ElMessage.success` | Auto-dismiss 3s |
| Operation failure | `ElMessage.error` | Show error message from backend |

---

## Vendor Management

### Backend additions needed

| Method | Status | Notes |
|--------|--------|-------|
| `create_vendor` | Exists in service, needs bridge exposure | Add to ApiBridge |
| `update_vendor` | Needs new service function + bridge | Standard update pattern |
| `disable_vendor` | Needs new service function + bridge | Set status='disabled', audit log |

### Frontend

- Vendor List page: filter by service_scope, text search
- Create/Edit via `VendorFormDialog` (el-dialog)
- Disable via `el-popconfirm` on action button
- No vendor deletion — disable only

---

## User Management

### Backend additions needed

| Method | Status | Notes |
|--------|--------|-------|
| `enable_user` | Needs new service function + bridge | Set status='active', audit log |

### Frontend (System page)

- Current user info: `el-descriptions` card
- User table (admin only): Machine ID, Name, Email, Role, Status (el-tag), Actions
- Create/Edit via `UserFormDialog` (el-dialog)
- Enable/Disable via `el-popconfirm`
- No user deletion — enable/disable only

---

## Desktop Features (Python Side)

### pywebview + WebView2

Update `app_shell.py` to use EdgeChromium directly (required for modern CSS and Vue):

```python
from webview.platforms.edgechromium import EdgeChrome

# Patch to configure WebView2 settings
_original_ready = EdgeChrome.on_webview_ready
def _patched_ready(self, sender, args):
    _original_ready(self, sender, args)
    if not args.IsSuccess:
        return
    settings = sender.CoreWebView2.Settings
    settings.AreBrowserAcceleratorKeysEnabled = False
    settings.AreDefaultContextMenusEnabled = True
    settings.AreDevToolsEnabled = False
EdgeChrome.on_webview_ready = _patched_ready
```

- `storage_path` set to `%LOCALAPPDATA%/sc-gr-management/webview2` for persistent localStorage

### Dev vs Production URL

```python
# app_shell.py
if DEV_MODE:
    url = "http://localhost:5173"      # Vite dev server
else:
    url = str(html_path)               # Built files
```

### Single Instance Detection

```python
# app_shell.py — startup
import ctypes
kernel32 = ctypes.windll.kernel32
MUTEX_NAME = "Local\\SC_GR_MANAGEMENT_INSTANCE"
mutex = kernel32.CreateMutexW(None, False, MUTEX_NAME)
if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
    # Find and activate existing window, then exit
    hwnd = ctypes.windll.user32.FindWindowW(None, "SC GR Management")
    if hwnd:
        ctypes.windll.user32.SetForegroundWindow(hwnd)
        ctypes.windll.user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    sys.exit(0)
```

### Minimize to Tray

- Install `pystray` dependency
- On window close event → `window.hide()` (not destroy)
- Tray icon with right-click menu: "Show Window" / "Exit"
- Double-click tray icon → restore window
- "Exit" menu → `window.destroy()` + cleanup

### Auto-Update Check

- Version: define `__version__` in `sc_gr_app/__init__.py`
- On startup, async fetch latest version from update server (timeout 3s, fail silently)
- If newer version → expose `check_update()` bridge method → frontend shows dialog
- User chooses: "Update Now" (download + replace + restart) or "Later"
- Update mechanism: download new installer/exe, launch it, exit current process

---

## Bridge API Surface

All Vue components call through `api/bridge.js`. The bridge module wraps every API call with unified error handling.

### API Methods (existing, unchanged)

| Bridge Method | Params | Used By |
|--------------|--------|---------|
| `current_user` | — | LoginView, AppHeader, useUser |
| `list_users` | — | SystemView |
| `create_user` | `{ data }` | SystemView → UserFormDialog |
| `update_user` | `{ machine_id, data }` | SystemView → UserFormDialog |
| `disable_user` | `{ machine_id }` | SystemView |
| `search_scs` | `{ text, filters, sort, direction, limit, offset }` | ScListView, HomeView |
| `get_sc_detail` | `{ sc_id }` | ScDetailView |
| `create_sc_draft` | `{ data }` | ScFormDialog |
| `submit_sc` | `{ data }` | ScFormDialog |
| `approve_sc` | `{ sc_id }` | ScDetailView |
| `deny_sc` | `{ sc_id }` | ScDetailView |
| `close_sc` | `{ sc_id }` | ScDetailView |
| `update_sc` | `{ data }` | ScFormDialog (edit) |
| `search_pos` | `{ text, filters, sort, direction, limit, offset }` | PoListView, ScDetailView |
| `get_po_detail` | `{ po_id }` | PoDetailView |
| `create_po` | `{ data }` | PoFormDialog |
| `update_po` | `{ data }` | PoFormDialog |
| `approve_po` | `{ po_id }` | PoDetailView |
| `finish_po` | `{ po_id }` | PoDetailView |
| `search_grs` | `{ text, filters, sort, direction, limit, offset }` | GrListView |
| `create_gr` | `{ data }` | GrFormDialog |
| `update_gr` | `{ data }` | GrFormDialog |
| `approve_gr` | `{ gr_id }` | PoDetailView |
| `cancel_gr` | `{ gr_id }` | PoDetailView |
| `search_vendors` | `{ text }` | VendorListView |
| `search_audit_logs` | `{ text, filters, sort, direction, limit, offset }` | LogsView, ScDetailView |
| `check_update` | — | App.vue (on mount) |

### New API Methods to Add

| Bridge Method | Params | Service Function | Notes |
|--------------|--------|-----------------|-------|
| `create_vendor` | `{ data }` | `vendor_service.create_vendor` | Already exists, expose in bridge |
| `update_vendor` | `{ vendor_id, data }` | New `update_vendor` | Add to service + bridge |
| `disable_vendor` | `{ vendor_id }` | New `disable_vendor` | Add to service + bridge |
| `enable_user` | `{ machine_id }` | New `enable_user` | Add to service + bridge |

---

## Component Usage Summary

| Current (Vanilla JS) | Element Plus | Notes |
|----------------------|-------------|-------|
| Manual `<table>` + `renderTable()` | `el-table` + `el-table-column` | Built-in sort, loading, empty |
| Manual `<select>` / `<input>` filters | `el-select` + `el-input` + `el-date-picker` | In FilterBar component |
| CSS `.status-badge` | `el-tag` with type mapping | Semantic color auto-mapping |
| Manual `<form>` in page | `el-dialog` + `el-form` | All forms in dialogs |
| `window.confirm()` | `el-message-box` / `el-popconfirm` | Consistent styling |
| `alert()` on error | `el-message` (toast) | Non-blocking |
| Manual modal-overlay div | `el-dialog` | Focus trap, ESC close |
| Manual drawer div | `el-drawer` (optional) | Quick row preview |
| Alpine.js `x-show`/`x-data` | Vue `v-if`/`ref`/`reactive` | Native Vue reactivity |
| Manual nav buttons | `el-menu` (router mode) | Auto high-light on route |
| Button CSS classes | `el-button` (primary/success/warning/danger) | Consistent sizing |
| Inline form in SC detail | `el-dialog` | Avoids page layout jumps |
| SC detail + PO/GR inline tree | `/sc/:id` → `/sc/:scId/po/:poId` separate pages | Cleaner navigation, less complexity |

---

## Theme & CSS Variables

Element Plus theme is customized via CSS variables in `main.css`, not by modifying Element Plus source.

```css
:root {
  /* Precision Dashboard overrides */
  --el-border-radius-base: 4px;
  --el-border-radius-small: 2px;
  
  /* Sidebar: dark background */
  --sidebar-bg: #1e293b;
  --sidebar-text: #cbd5e1;
  --sidebar-active: #3b82f6;
  
  /* Header */
  --header-height: 56px;
  
  /* Table */
  --table-header-bg: #f1f5f9;
  --table-row-hover: #f8fafc;
  --table-stripe: #fcfcfd;
  
  /* Status row left bar colors */
  --status-draft: #94a3b8;
  --status-pending: #f59e0b;
  --status-approved: #22c55e;
  --status-denied: #ef4444;
  --status-closed: #6b7280;
}
```

- Font: `system-ui, 'Segoe UI', sans-serif` — no external font download
- Tabular numbers: `.amount-value { font-variant-numeric: tabular-nums; }`
- Status row left bar: `border-left: 3px solid var(--status-<type>)` on `el-table` row class

---

## Implementation Phases

1. **Foundation**: Create `frontend/` with package.json, vite.config.js, index.html. Scaffold main.js, App.vue, router, bridge.js, composable stubs, main.css.
2. **Layout + Login**: SideNav.vue, AppHeader.vue, LoginView.vue — standalone login → main layout transition.
3. **List views**: ScListView, PoListView, GrListView, VendorListView, LogsView — each with FilterBar, table, pagination.
4. **Detail views**: ScDetailView (/sc/:id with SC info + compact PO table). PoDetailView (/sc/:scId/po/:poId with PO info + GR table).
5. **Dialogs**: ScFormDialog, PoFormDialog, GrFormDialog, VendorFormDialog, UserFormDialog — all el-dialog + el-form.
6. **Workbench**: HomeView — 2x2 card grid, role-dependent content, compact tables.
7. **System**: SystemView — current user info + user management (admin).
8. **Backend additions**: Expose create_vendor in bridge, add update_vendor + disable_vendor service methods, add enable_user service method.
9. **Desktop features**: Single instance mutex, pystray tray icon + menu, version check + update dialog. Update app_shell.py for WebView2 EdgeChromium, dev mode URL switching.
10. **Polish**: CSS variables, el-tag status mapping, tabular-nums, row left-bar colors, v-loading skeleton, empty states, animations. Remove old web/ files after build validation.
