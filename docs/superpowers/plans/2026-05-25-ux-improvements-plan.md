# UX Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 10 UX improvements incrementally: seed users, PicoCSS+Alpine integration, login screen, close modal, GR nesting, status badges, scroll fixes, vendor/requester dropdowns, and admin user management.

**Architecture:** Frontend receives PicoCSS v2 (class-light CSS framework) and Alpine.js v3 (declarative interactivity) via CDN. Backend gets 3 new bridge endpoints for user CRUD plus expanded seed data. Frontend views are refactored to use Alpine directives embedded in `innerHTML` strings while keeping `app.js` as the orchestrator.

**Tech Stack:** Python 3.11, pywebview, SQLite, vanilla JS ES modules, PicoCSS v2, Alpine.js v3

---

### Task 1: Expand Seed Users

**Files:**
- Modify: `sc_gr_app/services/user_service.py`
- Create: `tests/test_user_service.py` (if it doesn't exist; append seed tests)

- [ ] **Step 1: Read the current user_service.py to confirm starting state**

Run: `uv run pytest tests/ -q`
Expected: All existing tests pass.

- [ ] **Step 2: Write unit test for seed_users idempotency**

```python
# tests/test_user_service.py (append to existing file, or create if needed)
from sc_gr_app.services.user_service import seed_users

def test_seed_users_creates_users_when_empty(app_config):
    """seed_users inserts all six users when none exist."""
    from sc_gr_app.db.connection import connect
    seed_users(app_config)
    with connect(app_config) as conn:
        rows = conn.execute("select machine_id, user_name, role, email from users order by user_name").fetchall()
    assert len(rows) == 6
    assert rows[0]["machine_id"] == "V2SE7PP"
    assert rows[0]["user_name"] == "Li, Xingchen (C/EV-L)"
    assert rows[0]["role"] == "requester"
    assert rows[0]["email"] == "xingchen.li@audi.com.cn"

def test_seed_users_is_idempotent(app_config):
    """Calling seed_users twice does not duplicate users."""
    from sc_gr_app.db.connection import connect
    seed_users(app_config)
    seed_users(app_config)
    with connect(app_config) as conn:
        count = conn.execute("select count(*) as cnt from users").fetchone()["cnt"]
    assert count == 6
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_service.py -q`
Expected: FAIL — `seed_users` is not defined yet.

- [ ] **Step 4: Replace seed_default_admin with seed_users in user_service.py**

```python
# sc_gr_app/services/user_service.py
# Replace the existing seed_default_admin function and DEFAULT_ADMIN_USER_ID constant with:

SEED_USERS = [
    ("V2SE7PP", "Li, Xingchen (C/EV-L)", "requester", "xingchen.li@audi.com.cn"),
    ("UJWVFIH", "Su, Tong (C/EV-L)", "requester", "tong.su@audi.com.cn"),
    ("EYANQM0", "Yang, Qiaomin (C/EV-L)", "admin", "qiaomin.yang@audi.com.cn"),
    ("FO5LZ6P", "Ye, Xiaorui (C/EV-L)", "requester", "xiaorui.ye@audi.com.cn"),
    ("EZHOLW0", "Zhou, Liwei (C/EV-L)", "requester", "liwei.zhou@audi.com.cn"),
    ("FPBTMS5", "Sun, Jialing (C/EV-L)", "admin", "jialing.sun@audi.com.cn"),
]


def seed_users(config: AppConfig) -> None:
    timestamp = now()
    with connect(config) as conn:
        for machine_id, user_name, role, email in SEED_USERS:
            existing = conn.execute(
                "select user_id from users where machine_id = ?",
                (machine_id,),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                insert into users (
                  user_id, machine_id, user_name, role, email, status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (f"U-{machine_id}", machine_id, user_name, role, email, timestamp, timestamp),
            )
        conn.commit()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_user_service.py -q`
Expected: PASS

- [ ] **Step 6: Update the caller in main.py (or wherever seed_default_admin is called)**

```bash
# Find the caller
```
Run: `grep -rn "seed_default_admin" sc_gr_app/`

If in `sc_gr_app/main.py`, update:
```python
# Change this line:
from sc_gr_app.services.user_service import seed_default_admin
# To:
from sc_gr_app.services.user_service import seed_users

# Change this call:
seed_default_admin(config)
# To:
seed_users(config)
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add sc_gr_app/services/user_service.py sc_gr_app/main.py tests/test_user_service.py
git commit -m "feat: replace seed_default_admin with seed_users for six initial users"
```

---

### Task 2: Add PicoCSS + Alpine.js CDN Links and Strip Redundant CSS

**Files:**
- Modify: `sc_gr_app/web/index.html`
- Modify: `sc_gr_app/web/styles.css`

- [ ] **Step 1: Add CDN links to index.html**

In `sc_gr_app/web/index.html`, add PicoCSS and Alpine.js before the existing stylesheet:

```html
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SC GR Management</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@picocss/pico@2/css/pico.min.css">
  <link rel="stylesheet" href="./styles.css">
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>
</head>
```

- [ ] **Step 2: Strip CSS variables and base styles that PicoCSS covers**

In `sc_gr_app/web/styles.css`, remove the `:root` block (lines 1-13) — PicoCSS provides its own design tokens. Remove the universal `*` rule (line 15-17) — Pico handles box-sizing. Remove `html, body` styles (lines 19-30) — Pico handles typography. Remove `button, input, select` font inherit (lines 32-36) — Pico handles this. Keep `button { cursor: pointer; }` override.

Remove generic `input, select, textarea` styles (lines 204-222) — PicoCSS styles these. Remove `.button` base, `.button:hover`, `.button.primary`, `.button.primary:hover` (lines 229-256) — PicoCSS provides these. Remove `.icon-button` (lines 258-268) — Pico provides button styling.

**Keep:** `.sr-only`, `.app-shell`, `.side-nav`, `.brand-*`, `.nav-*`, `.workspace`, `.top-toolbar`, `.toolbar-main`, heading overrides, `.search-box`, `.user-panel`, `.auth-dot`, `.content`, `.view-region`, `.summary-grid`, `.metric-*`, `.filter-*`, `.table-*`, `.status-badge` and status color classes, `.amount`, `.state-panel`, `.detail-drawer`, `.drawer-*`, `.detail-row`, `.detail-label`, `.detail-value`, `.detail-page`, `.detail-page-header`, `.detail-section`, `.section-toolbar`, `.form-grid`, `.form-field`, `.actions`, `.sc-form`, `.inline-record-form`, `.row-actions`, `.button.compact`, `.detail-grid`, `.detail-table`, `.empty-note`, `.muted-text`, `.home-intro`.

- [ ] **Step 3: Add new CSS for items not covered by Pico**

Append to `styles.css`:

```css
/* Danger button variant */
.button.danger {
  border-color: var(--pico-del-color, #c2413b);
  color: var(--pico-del-color, #c2413b);
  background: var(--pico-del-background, #fde5e3);
}
.button.danger:hover {
  background: #f5c6cb;
}

/* Status row left borders */
.status-row {
  border-left: 4px solid transparent;
}
.status-row.status-approved,
.status-row.status-finished,
.status-row.status-closed,
.status-row.status-active {
  border-left-color: var(--success);
}
.status-row.status-pending,
.status-row.status-po_pending,
.status-row.status-created {
  border-left-color: var(--warning);
}
.status-row.status-denied,
.status-row.status-cancelled,
.status-row.status-disabled {
  border-left-color: var(--danger);
}
.status-row.status-po_approved,
.status-row.status-submitted {
  border-left-color: var(--primary);
}

/* PO tree expand row */
.po-parent-row {
  cursor: pointer;
  user-select: none;
}
.po-parent-row:hover td {
  background: var(--surface-muted);
}
.po-expand-icon {
  display: inline-block;
  width: 18px;
  font-size: 11px;
  transition: transform 0.15s;
}
.po-expand-icon.expanded {
  transform: rotate(90deg);
}

/* GR child row indent */
.gr-child-row td:first-child {
  padding-left: 32px;
}

/* Modal overlay */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.45);
}
.modal-overlay .modal-card {
  width: min(480px, 94vw);
  padding: 24px;
  border-radius: 12px;
  background: var(--surface);
  box-shadow: 0 8px 40px rgba(0, 0, 0, 0.18);
}
.modal-card h3 {
  margin-bottom: 12px;
}
.modal-card .modal-body {
  margin-bottom: 18px;
  line-height: 1.55;
}
.modal-card .modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Login screen */
.login-screen {
  min-height: 100vh;
  display: grid;
  place-items: center;
  background: var(--bg);
}
.login-card {
  width: min(420px, 94vw);
  padding: 32px;
  border: 1px solid var(--line);
  border-radius: 12px;
  background: var(--surface);
  text-align: center;
}
.login-card .login-icon {
  font-size: 48px;
  margin-bottom: 16px;
}
.login-card .login-detail {
  margin-top: 12px;
  padding: 10px;
  border-radius: 8px;
  background: var(--surface-muted);
  font-size: 12px;
  color: var(--muted);
}

/* System view user management */
.user-mgmt-section {
  margin-top: 18px;
}
.user-mgmt-section .inline-user-form {
  padding: 12px;
  margin-top: 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface-muted);
}

/* Fix: overflow-x auto on detail sections */
.detail-section {
  overflow-x: auto;
}
.section-toolbar {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--surface);
  padding: 4px 0;
}
.section-toolbar .toolbar-actions {
  flex-shrink: 0;
}
```

**Design tokens note:** PicoCSS uses different variable names than the current custom properties. Map current CSS variables to Pico equivalents or keep the existing `--bg`, `--surface`, `--text`, `--muted`, `--line`, `--primary`, `--primary-soft`, `--success`, `--warning`, `--danger` variables since our custom CSS still references them extensively. Add a `:root` block that extends Pico:

```css
:root {
  --bg: var(--pico-background-color, #f7f9fc);
  --surface: var(--pico-card-background-color, #ffffff);
  --surface-muted: var(--pico-secondary-background, #eef3f8);
  --text: var(--pico-color, #1d2733);
  --muted: var(--pico-secondary, #667789);
  --line: var(--pico-card-border-color, #d8e1ea);
  --primary: var(--pico-primary, #1f73d1);
  --primary-soft: #dcecff;
  --success: #16875d;
  --warning: #b7791f;
  --danger: #c2413b;
}
```

- [ ] **Step 4: Verify the app starts**

Run: `uv run python -m sc_gr_app.main`
Expected: App window opens. Styles may look different (PicoCSS taking over), but layout should work.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/web/index.html sc_gr_app/web/styles.css
git commit -m "feat: add PicoCSS v2 and Alpine.js v3, reconcile CSS variables"
```

---

### Task 3: Login Screen

**Files:**
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/styles.css` (login styles added in Task 2)

- [ ] **Step 1: Add renderLoginScreen function to views.js**

Append to `sc_gr_app/web/components/views.js`:

```javascript
export function renderLoginScreen() {
  const appShell = document.querySelector(".app-shell");
  appShell.innerHTML = `
    <div class="login-screen" x-data="{ state: 'loading', userName: '', role: '', machineId: '', error: '' }" x-init="(async () => {
      try {
        const result = await window.pywebview.api.current_user();
        const data = JSON.parse(result);
        if (data.ok) {
          userName = data.data.user_name;
          role = data.data.role;
          machineId = data.data.machine_id;
          state = 'authorized';
        } else {
          state = 'unauthorized';
          machineId = data.error?.message ?? 'Unknown error';
        }
      } catch (e) {
        state = 'unauthorized';
        machineId = 'Bridge unavailable';
      }
    })()">
      <div class="login-card">
        <div class="login-icon">SG</div>
        <h2>SC GR Operations</h2>

        <div x-show="state === 'loading'">
          <p aria-busy="true">Verifying identity...</p>
        </div>

        <div x-show="state === 'authorized'" x-cloak>
          <p style="color: var(--success); font-weight: 700;">Identity Verified</p>
          <p>Welcome, <strong x-text="userName"></strong></p>
          <p class="muted-text" x-text="role + ' | ' + machineId"></p>
          <button type="button" class="button primary" style="margin-top: 16px;" @click="
            document.querySelector('.app-shell').innerHTML = '';
            window.__loginComplete = true;
          ">Enter System</button>
        </div>

        <div x-show="state === 'unauthorized'" x-cloak>
          <p style="color: var(--danger); font-weight: 700;">Not Authorized</p>
          <p>Your machine ID <strong x-text="machineId"></strong> is not recognized.</p>
          <p class="muted-text">Please contact an administrator to gain access.</p>
        </div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 2: Modify app.js startup flow**

In `sc_gr_app/web/app.js`, change the startup section (lines 378-385):

```javascript
// Replace:
renderNavigation();
renderUserPanel();
await loadCurrentUser();
if (state.user) {
  await routeTo("sc");
} else {
  await routeTo("system");
}

// With:
import { renderLoginScreen } from "./components/views.js";

// At the bottom, replace the startup block:
(async function startup() {
  renderLoginScreen();

  // Wait for Alpine to process the login card and user to click "Enter System"
  await new Promise((resolve) => {
    const check = () => {
      if (window.__loginComplete) {
        resolve();
      } else {
        setTimeout(check, 100);
      }
    };
    check();
  });

  // Now restore the app shell
  const appShell = document.querySelector(".app-shell");
  appShell.innerHTML = `
    <aside class="side-nav" aria-label="Primary navigation">
      <div class="brand-block">
        <div class="brand-mark">SG</div>
        <div>
          <div class="brand-title">SC GR</div>
          <div class="brand-subtitle">Operations</div>
        </div>
      </div>
      <nav id="nav" class="nav-list"></nav>
    </aside>
    <div class="workspace">
      <header class="top-toolbar">
        <div class="toolbar-main" id="toolbar">
          <div>
            <div class="eyebrow">Workspace</div>
            <h1 id="view-title">SC</h1>
          </div>
        </div>
        <form id="global-search-form" class="search-box" role="search">
          <label class="sr-only" for="global-search">Search current view</label>
          <input id="global-search" type="search" autocomplete="off" placeholder="Search current view">
          <button type="submit" class="button primary">Search</button>
        </form>
        <div id="user-panel" class="user-panel" aria-live="polite">
          <span class="auth-dot waiting"></span>
          <span>Checking authorization</span>
        </div>
      </header>
      <main class="content" id="main-content">
        <section id="home-view" class="view-region"></section>
        <section id="filters" class="filter-region" aria-label="Filters"></section>
        <section id="table-region" class="table-region"></section>
      </main>
    </div>
    <aside id="detail-drawer" class="detail-drawer" aria-label="Record detail" hidden>
      <div class="drawer-header">
        <div>
          <div class="eyebrow">Detail</div>
          <h2 id="drawer-title">Record</h2>
        </div>
        <button id="drawer-close" type="button" class="icon-button" aria-label="Close detail drawer">x</button>
      </div>
      <div id="drawer-content" class="drawer-content"></div>
    </aside>
  `;

  // Re-query all DOM references since the shell was rebuilt
  elements.nav = document.querySelector("#nav");
  elements.title = document.querySelector("#view-title");
  elements.toolbar = document.querySelector("#toolbar");
  elements.userPanel = document.querySelector("#user-panel");
  elements.searchForm = document.querySelector("#global-search-form");
  elements.searchInput = document.querySelector("#global-search");
  elements.home = document.querySelector("#home-view");
  elements.filters = document.querySelector("#filters");
  elements.table = document.querySelector("#table-region");
  elements.drawer.root = document.querySelector("#detail-drawer");
  elements.drawer.title = document.querySelector("#drawer-title");
  elements.drawer.content = document.querySelector("#drawer-content");
  elements.drawer.close = document.querySelector("#drawer-close");

  // Re-bind drawer close
  elements.drawer.close.addEventListener("click", () => {
    elements.drawer.root.hidden = true;
  });

  // Re-bind search events
  elements.searchForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    state.globalSearch = elements.searchInput.value.trim();
    await renderActiveView();
  });
  elements.searchInput.addEventListener("search", async () => {
    state.globalSearch = elements.searchInput.value.trim();
    await renderActiveView();
  });

  renderNavigation();
  await loadCurrentUser();
  renderUserPanel();

  if (state.user) {
    await routeTo("sc");
  } else {
    await routeTo("system");
  }
})();
```

Note: The startup `await loadCurrentUser(); if (state.user) ...` at the bottom of app.js (lines 378-385) must be removed since the IIFE replaces it. Also remove the `renderNavigation(); renderUserPanel();` lines that precede it.

- [ ] **Step 3: Verify the app shows login screen then transitions**

Run: `uv run python -m sc_gr_app.main`
Expected: Login screen appears → "Verifying identity..." → "Welcome, [Name]" with Enter button. Click Enter → normal app shell appears.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/web/app.js sc_gr_app/web/components/views.js
git commit -m "feat: add login screen gate before main app"
```

---

### Task 4: Close Confirmation Modal

**Files:**
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/components/state.js`

- [ ] **Step 1: Add confirmingClose to state.js**

In `sc_gr_app/web/components/state.js`, add `confirmingClose: false` to `state.scDetail`:

```javascript
scDetail: {
    scId: null,
    poId: null,
    grId: null,
    record: null,
    loading: false,
    error: null,
    actionPending: null,
    actionError: null,
    editMode: false,
    confirmingClose: false,   // <-- add this line
},
```

Also add to `setScDetailTarget` and `clearScDetailTarget`:
```javascript
state.scDetail.confirmingClose = false;
```

- [ ] **Step 2: Add renderCloseModal function to views.js**

Append to `sc_gr_app/web/components/views.js`:

```javascript
export function renderCloseModal(scNo) {
  return `
    <div class="modal-overlay" x-data="{ confirmationText: '' }" @keydown.escape.window="$el.remove()">
      <div class="modal-card" @click.outside="$el.parentElement.remove()">
        <h3>Close SC ${escapeHtml(scNo)}?</h3>
        <div class="modal-body">
          <p style="color: var(--danger); font-weight: 700;">This action cannot be undone.</p>
          <p>This SC will be permanently closed. No further PO or GR operations will be possible.</p>
          <p class="muted-text" style="margin-top: 12px;">Type <strong>I CONFIRM CLOSE THIS SC</strong> to proceed.</p>
          <input
            type="text"
            x-model="confirmationText"
            placeholder="I CONFIRM CLOSE THIS SC"
            style="margin-top: 8px;"
            autofocus
          >
        </div>
        <div class="modal-actions">
          <button
            type="button"
            class="button danger"
            :disabled="confirmationText !== 'I CONFIRM CLOSE THIS SC'"
            @click="
              $el.parentElement.parentElement.parentElement.remove();
              window.__closeConfirmed = true;
            "
          >Close SC</button>
          <button
            type="button"
            class="button"
            @click="$el.parentElement.parentElement.parentElement.remove()"
          >Cancel</button>
        </div>
      </div>
    </div>
  `;
}
```

- [ ] **Step 3: Modify handleScAction in app.js for close with modal**

In `sc_gr_app/web/app.js`, replace the close case in `handleScAction`:

```javascript
async function handleScAction(action) {
  const scId = state.scDetail.record?.sc?.sc_id ?? state.scDetail.scId;
  if (!scId) {
    return;
  }
  if (action === "deny" && !window.confirm("Deny this SC?")) {
    return;
  }
  if (action === "close") {
    // Show custom modal instead of window.confirm
    const scNo = state.scDetail.record?.sc?.sc_no ?? scId;
    const modalHtml = renderCloseModal(scNo);
    const container = document.createElement("div");
    container.innerHTML = modalHtml;
    document.body.appendChild(container.firstElementChild);

    window.__closeConfirmed = false;
    await new Promise((resolve) => {
      const check = () => {
        if (window.__closeConfirmed) {
          resolve();
        } else if (!document.querySelector(".modal-overlay")) {
          // User dismissed the modal
          resolve();
        } else {
          setTimeout(check, 100);
        }
      };
      check();
    });

    if (!window.__closeConfirmed) {
      return;
    }
    window.__closeConfirmed = false;
  }

  // ... rest of function unchanged
```

Add import at top of app.js:
```javascript
import { renderCloseModal } from "./components/views.js";
```

- [ ] **Step 4: Make Close button red**

In `sc_gr_app/web/components/views.js`, in the `scActionButton` function, add danger class for close:

```javascript
function scActionButton(action, label, enabled, pending = null, primary = false) {
  if (!enabled) {
    return "";
  }
  const disabled = pending ? " disabled" : "";
  const pendingText = pending === action ? "..." : "";
  const dangerClass = action === "close" ? " danger" : "";
  const primaryClass = action === "close" ? "" : (primary ? " primary" : "");
  return `<button type="button" class="button${primaryClass}${dangerClass}" data-sc-action="${escapeHtml(action)}"${disabled}>${escapeHtml(label)}${pendingText}</button>`;
}
```

- [ ] **Step 5: Verify**

Run: `uv run python -m sc_gr_app.main`
Expected: Open an SC → Close button is red → click → modal appears with text input → button disabled until correct text → "I CONFIRM CLOSE THIS SC" typed → button enabled → click → SC closes.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/web/app.js sc_gr_app/web/components/views.js sc_gr_app/web/components/state.js
git commit -m "feat: add close confirmation modal with text validation"
```

---

### Task 5: GR Nesting Under PO (Tree Layout)

**Files:**
- Modify: `sc_gr_app/web/components/views.js`

- [ ] **Step 1: Replace renderPoSection to include nested GRs**

In `sc_gr_app/web/components/views.js`, replace `renderPoSection`:

```javascript
function renderPoSection(detail, formState, pending) {
  const canManagePo = Boolean(detail.permissions?.can_manage_po);
  const canManageGr = Boolean(detail.permissions?.can_manage_gr);
  const pos = detail.pos ?? [];
  const grs = detail.grs ?? [];

  if (!pos.length) {
    return `
      <section class="detail-section po-section">
        <div class="section-toolbar">
          <h3>PO / GR</h3>
          ${canManagePo && !formState ? `<button type="button" class="button" data-po-form-open="create"${pending ? " disabled" : ""}>Add PO</button>` : ""}
        </div>
        <p class="empty-note">No PO records.</p>
      </section>
    `;
  }

  const form = formState ? renderPoForm(detail.sc, formState, pending) : "";

  const posHtml = pos.map((po) => {
    const poGrs = grs.filter((gr) => String(gr.po_id) === String(po.po_id));
    const poId = escapeHtml(text(po.po_id));
    return `
      <div class="po-group" x-data="{ expanded: false }">
        <table class="data-table detail-table">
          <tbody>
            <tr class="status-row status-${escapeHtml(po.status)} po-parent-row" @click="expanded = !expanded">
              <td style="width: 36px;">
                <span class="po-expand-icon" :class="{ 'expanded': expanded }">▶</span>
              </td>
              <td>${statusBadge(po.status)}</td>
              <td>${escapeHtml(text(po.po_no ?? po.po_id))}</td>
              <td>${escapeHtml(text(po.vendor_id))}</td>
              <td class="amount">${money(po.po_amount)}</td>
              <td class="amount">${money(po.open_po_amount)}</td>
              <td>${date(po.contract_from)}</td>
              <td>${date(po.contract_to)}</td>
              <td>
                <div class="row-actions">
                  ${renderPoRowActions(po, detail, pending)}
                  ${canManageGr ? `<button type="button" class="button compact" data-gr-form-open="create" data-po-id="${poId}" x-show="expanded"${pending ? " disabled" : ""}>Add GR</button>` : ""}
                </div>
              </td>
            </tr>
            ${poGrs.map((gr) => `
              <tr class="status-row status-${escapeHtml(gr.status)} gr-child-row" x-show="expanded">
                <td></td>
                <td>${statusBadge(gr.status)}</td>
                <td>${escapeHtml(text(gr.gr_id))}</td>
                <td>${escapeHtml(text(gr.requester_id))}</td>
                <td class="amount">${money(gr.estimated_amount)}</td>
                <td class="amount">${money(gr.con_value)}</td>
                <td>${escapeHtml(text(gr.remark))}</td>
                <td>${date(gr.created_at)}</td>
                <td><div class="row-actions">${renderGrRowActions(gr, detail, pending)}</div></td>
              </tr>
            `).join("")}
            ${poGrs.length === 0 ? `
              <tr class="gr-child-row" x-show="expanded">
                <td></td>
                <td colspan="8"><span class="empty-note">No GRs for this PO.</span></td>
              </tr>
            ` : ""}
          </tbody>
        </table>
        ${formState && formState.poId === po.po_id ? renderGrForm(detail, formState, pending, po.po_id) : ""}
      </div>
    `;
  }).join("");

  return `
    <section class="detail-section po-section">
      <div class="section-toolbar">
        <h3>PO / GR</h3>
        ${canManagePo && !formState ? `<button type="button" class="button" data-po-form-open="create"${pending ? " disabled" : ""}>Add PO</button>` : ""}
      </div>
      ${form}
      ${posHtml}
    </section>
  `;
}
```

- [ ] **Step 2: Update renderGrForm to accept explicit poId parameter**

Modify `renderGrForm` signature and remove the po_id dropdown (since it's pre-determined):

```javascript
function renderGrForm(detail, formState, pending, parentPoId = null) {
  const record = formState.record ?? {};
  const poId = parentPoId ?? formState.poId ?? state.scDetail.poId ?? detail.pos?.[0]?.po_id ?? "";
  const disabled = pending ? " disabled" : "";
  return `
    <form class="inline-record-form gr-form" data-gr-form data-mode="${escapeHtml(formState.mode)}" data-po-id="${escapeHtml(poId)}">
      <div class="form-grid">
        ${field("gr_id", "GR ID", record.gr_id ?? "", "text", { readonly: formState.mode === "edit", required: true })}
        ${field("po_id", "PO ID", poId, "hidden")}
        ${field("requester_id", "Requester ID", record.requester_id ?? state.user?.user_id ?? "")}
        ${field("estimated_amount", "Estimated Amount", record.estimated_amount ?? "", "number")}
        ${field("con_value", "Con Value", record.con_value ?? "", "number")}
        <label class="form-field full">
          <span>Remark</span>
          <textarea name="remark"${disabled}>${escapeHtml(text(record.remark))}</textarea>
        </label>
      </div>
      <div class="actions">
        <button type="submit" class="button primary"${disabled}>Save${pending === "gr-save" ? "..." : ""}</button>
        <button type="button" class="button" data-gr-form-cancel${disabled}>Cancel</button>
      </div>
    </form>
  `;
}
```

- [ ] **Step 3: Update openGrForm in app.js to track parent PO**

In `sc_gr_app/web/app.js`, update `openGrForm`:

```javascript
async function openGrForm(mode, row = null) {
  state.scDetail.editMode = false;
  state.scDetail.actionError = null;
  scDetailUi.poForm = null;
  const poId = row?.poId ?? state.scDetail.poId ?? state.scDetail.record?.pos?.[0]?.po_id ?? null;
  scDetailUi.grForm = {
    mode,
    record: mode === "edit" ? row ?? {} : {},
    poId: poId,
  };
  await renderActiveView();
}
```

- [ ] **Step 4: Update event binding in renderScDetail for the new GR buttons**

In `renderScDetail`, update the GR form open button binding to handle the data-po-id:

```javascript
regions.home.querySelectorAll("[data-gr-form-open]").forEach((button) => {
  button.addEventListener("click", async () => {
    const row = findGr(detail, button.dataset.grId);
    await callbacks.onGrFormOpen?.(button.dataset.grFormOpen, { ...row, poId: button.dataset.poId });
  });
});
```

- [ ] **Step 5: Remove standalone renderGrSection call from renderScDetail**

In `renderScDetail`, remove the line:
```javascript
${renderGrSection(detail, callbacks.grForm, pending)}
```

- [ ] **Step 6: Verify**

Run: `uv run python -m sc_gr_app.main`
Expected: Open an SC with POs and GRs → PO rows show expand chevron → click PO row → GRs appear nested underneath → "Add GR" button per PO → expand/collapse works.

- [ ] **Step 7: Commit**

```bash
git add sc_gr_app/web/components/views.js sc_gr_app/web/app.js
git commit -m "feat: nest GRs under parent PO rows with tree expand/collapse"
```

---

### Task 6: PO/GR Status Badges with Colored Left Border

**Files:**
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/styles.css` (already added `.status-row` styles in Task 2)

- [ ] **Step 1: Verify status badges and borders are rendered**

The tree layout from Task 5 already includes `status-row status-{raw_status}` classes on `<tr>` elements and `statusBadge()` as the first data column. The CSS from Task 2 already provides the left border colors.

Run: `uv run python -m sc_gr_app.main`
Expected: Open SC detail → PO and GR rows have colored left borders matching their status. Status badge pill is the first visible column.

- [ ] **Step 2: Commit**

```bash
git add sc_gr_app/web/components/views.js
git commit -m "feat: add colored status left borders and badge-first column order"
```

---

### Task 7: Form Scroll Behavior

**Files:**
- Modify: `sc_gr_app/web/styles.css` (already done in Task 2 — verify)

- [ ] **Step 1: Verify overflow-x auto and sticky toolbar**

The CSS changes from Task 2 already set `.detail-section { overflow-x: auto; }` and `.section-toolbar { position: sticky; top: 0; }`. Verify they're applied.

Run: `uv run python -m sc_gr_app.main`
Expected: Narrow the window or open a form with many fields → horizontal scrollbar appears in the section card → action buttons stay in view on the right.

- [ ] **Step 2: Commit** (skip if no changes needed — already in Task 2 commit)

---

### Task 8: Vendor Selection as Dropdown in PO Form

**Files:**
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/components/state.js`

- [ ] **Step 1: Add vendors to state**

In `sc_gr_app/web/components/state.js`, add `vendors: []` to `state`:

```javascript
export const state = {
  // ... existing fields ...
  vendors: [],
  users: [],
  // ...
};
```

- [ ] **Step 2: Fetch vendors in app.js when entering SC detail**

In `sc_gr_app/web/app.js`, modify `refreshScDetail`:

```javascript
async function refreshScDetail() {
  await loadScDetail();
  // Fetch vendors for PO form dropdown
  if (state.scDetail.record && !state.vendors.length) {
    try {
      state.vendors = await callApi("search_vendors", { limit: 500 });
    } catch {
      state.vendors = [];
    }
  }
  await renderActiveView();
}
```

- [ ] **Step 3: Update renderPoForm to use vendor select**

In `sc_gr_app/web/components/views.js`, replace the `vendor_id` field in `renderPoForm`:

```javascript
function renderVendorSelect(vendors, currentValue) {
  if (!vendors.length) {
    return `<p class="empty-note">No vendors available. Add vendors in Vendor Management first.</p>`;
  }
  const options = [`<option value="">-- Select Vendor --</option>`]
    .concat(vendors.map((v) => {
      const vid = escapeHtml(text(v.vendor_id));
      const label = escapeHtml(`${text(v.vendor_name)} — KSRM: ${text(v.ksrm_vendor_code)}`);
      const selected = vid === currentValue ? " selected" : "";
      return `<option value="${vid}"${selected}>${label}</option>`;
    }))
    .join("");
  return `
    <label class="form-field">
      <span>Vendor</span>
      <select name="vendor_id" required>${options}</select>
    </label>
  `;
}
```

Then in `renderPoForm`, replace:
```javascript
${field("vendor_id", "Vendor ID", record.vendor_id ?? "", "text", { required: true })}
```
With:
```javascript
${renderVendorSelect(state.vendors, record.vendor_id ?? "")}
```

- [ ] **Step 4: Verify**

Run: `uv run python -m sc_gr_app.main`
Expected: Open SC → Add PO → Vendor field is a dropdown showing existing vendors → select one → save → PO created with vendor.

- [ ] **Step 5: Commit**

```bash
git add sc_gr_app/web/components/views.js sc_gr_app/web/app.js sc_gr_app/web/components/state.js
git commit -m "feat: replace vendor_id text input with vendor select dropdown in PO form"
```

---

### Task 9: Requester Selection as Dropdown in SC Form

**Files:**
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/components/state.js` (already added `users: []` in Task 8)

- [ ] **Step 1: Fetch users at app startup**

In the startup IIFE in `sc_gr_app/web/app.js`, after `await loadCurrentUser();`:

```javascript
try {
  state.users = await callApi("list_users", {});
} catch {
  state.users = [];
}
```

(Requires `list_users` endpoint — added in Step 2 below.)

- [ ] **Step 2: Add list_users endpoint to bridge.py**

In `sc_gr_app/web/components/..` — no, this is a backend change. Add to `sc_gr_app/services/user_service.py`:

```python
def list_active_users(config: AppConfig) -> list[dict]:
    with connect(config) as conn:
        rows = conn.execute(
            "select user_id, machine_id, user_name, role, email, status from users where status = 'active' order by user_name"
        ).fetchall()
    return [dict(row) for row in rows]
```

Add to `sc_gr_app/api/bridge.py`:

```python
def list_users(self, payload=None) -> dict:
    try:
        self._require_current_user()
        from sc_gr_app.services.user_service import list_active_users
        return ok(list_active_users(self.config))
    except Exception as exc:
        return fail(exc)
```

- [ ] **Step 3: Fetch users at startup in app.js**

In the startup IIFE, after `await loadCurrentUser();`:

```javascript
try {
  state.users = await callApi("list_users", {});
} catch {
  state.users = [];
}
```

- [ ] **Step 4: Update renderNewSc and renderScEditForm to use requester select**

Create a helper in `views.js`:

```javascript
function renderRequesterSelect(users, currentValue) {
  const activeUsers = users || [];
  if (!activeUsers.length) {
    return field("requester_id", "Requester", currentValue, "text", { required: true });
  }
  const options = [`<option value="">-- Select Requester --</option>`]
    .concat(activeUsers.map((u) => {
      const mid = escapeHtml(text(u.machine_id));
      const label = escapeHtml(`${text(u.user_name)} — ${mid}`);
      const selected = mid === currentValue ? " selected" : "";
      return `<option value="${mid}"${selected}>${label}</option>`;
    }))
    .join("");
  return `
    <label class="form-field">
      <span>Requester</span>
      <select name="requester_id" required>${options}</select>
    </label>
  `;
}
```

In `renderNewSc`, replace:
```javascript
${field("requester_id", "Requester", state.user?.user_id ?? "", "text", { readonly: true, required: true })}
```
With:
```javascript
${renderRequesterSelect(state.users, state.user?.machine_id ?? "")}
```

In `renderScEditForm`, add requester field (currently it's not in the edit form — add it after `field("sc_no", ...)`):
```javascript
${renderRequesterSelect(state.users, sc.requester_id ?? "")}
```

- [ ] **Step 5: Verify**

Run: `uv run python -m sc_gr_app.main`
Expected: Create new SC → Requester field is a dropdown with all users → Edit SC → Requester dropdown also present → select a user → save.

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/services/user_service.py sc_gr_app/api/bridge.py sc_gr_app/web/components/views.js sc_gr_app/web/app.js
git commit -m "feat: add requester select dropdown in SC create/edit forms, list_users endpoint"
```

---

### Task 10: User Management in System View

**Files:**
- Modify: `sc_gr_app/services/user_service.py` (already added `list_active_users`, add `create_user`, `update_user`, `disable_user`)
- Modify: `sc_gr_app/api/bridge.py` (already added `list_users`, add `create_user`, `update_user`, `disable_user`)
- Modify: `sc_gr_app/web/components/views.js` — expand `renderSystem`
- Modify: `sc_gr_app/web/styles.css` — already added `.user-mgmt-section` in Task 2

- [ ] **Step 1: Write backend tests for user CRUD**

```python
# tests/test_user_service.py (append)

def test_create_user(app_config):
    from sc_gr_app.services.user_service import create_user
    from sc_gr_app.db.connection import connect
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    create_user(app_config, current_user, {
        "machine_id": "NEWUSER",
        "user_name": "Test User",
        "email": "test@example.com",
        "role": "requester",
    })
    with connect(app_config) as conn:
        row = conn.execute("select * from users where machine_id = ?", ("NEWUSER",)).fetchone()
    assert row is not None
    assert row["user_name"] == "Test User"
    assert row["role"] == "requester"
    assert row["status"] == "active"

def test_create_user_requires_admin(app_config):
    from sc_gr_app.services.user_service import create_user
    from sc_gr_app.errors import PermissionDenied
    import pytest
    current_user = {"user_id": "U-REQ", "role": "requester", "machine_id": "REQ001"}
    with pytest.raises(PermissionDenied):
        create_user(app_config, current_user, {
            "machine_id": "NEWUSER",
            "user_name": "Test",
            "email": "t@t.com",
            "role": "requester",
        })

def test_update_user(app_config):
    from sc_gr_app.services.user_service import update_user, create_user
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    create_user(app_config, current_user, {
        "machine_id": "EDITME",
        "user_name": "Original",
        "email": "old@example.com",
        "role": "requester",
    })
    update_user(app_config, current_user, "EDITME", {
        "user_name": "Updated Name",
        "email": "new@example.com",
    })
    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        row = conn.execute("select * from users where machine_id = ?", ("EDITME",)).fetchone()
    assert row["user_name"] == "Updated Name"
    assert row["email"] == "new@example.com"

def test_disable_user(app_config):
    from sc_gr_app.services.user_service import disable_user, create_user
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    create_user(app_config, current_user, {
        "machine_id": "DISABLEME",
        "user_name": "To Disable",
        "email": "d@d.com",
        "role": "requester",
    })
    disable_user(app_config, current_user, "DISABLEME")
    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        row = conn.execute("select status from users where machine_id = ?", ("DISABLEME",)).fetchone()
    assert row["status"] == "disabled"

def test_seed_users_includes_all_six(app_config):
    from sc_gr_app.services.user_service import seed_users
    from sc_gr_app.db.connection import connect
    seed_users(app_config)
    with connect(app_config) as conn:
        rows = conn.execute("select machine_id from users order by user_name").fetchall()
    machine_ids = {r["machine_id"] for r in rows}
    assert "V2SE7PP" in machine_ids
    assert "UJWVFIH" in machine_ids
    assert "EYANQM0" in machine_ids
    assert "FO5LZ6P" in machine_ids
    assert "EZHOLW0" in machine_ids
    assert "FPBTMS5" in machine_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_user_service.py -q`
Expected: FAIL — `create_user`, `update_user`, `disable_user` not defined.

- [ ] **Step 3: Implement create_user, update_user, disable_user in user_service.py**

```python
# sc_gr_app/services/user_service.py (append)

def create_user(config: AppConfig, current_user: dict, data: dict) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can create users")
    machine_id = data["machine_id"]
    user_name = data["user_name"]
    email = data.get("email")
    role = data["role"]
    if role not in ("admin", "requester"):
        raise ValidationError("role must be 'admin' or 'requester'")
    user_id = f"U-{machine_id}"
    timestamp = now()
    with connect(config) as conn:
        existing = conn.execute(
            "select user_id from users where machine_id = ?",
            (machine_id,),
        ).fetchone()
        if existing:
            raise ValidationError(f"User with machine_id {machine_id} already exists")
        conn.execute(
            """
            insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (user_id, machine_id, user_name, role, email, timestamp, timestamp),
        )
        write_audit_log(
            conn,
            action_type="create_user",
            object_type="user",
            object_id=user_id,
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=None,
            after={"user_id": user_id, "machine_id": machine_id, "user_name": user_name, "role": role, "email": email},
        )
        conn.commit()
    return {"user_id": user_id, "machine_id": machine_id, "user_name": user_name, "role": role, "email": email, "status": "active"}


def update_user(config: AppConfig, current_user: dict, machine_id: str, data: dict) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can update users")
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()
        if not row:
            raise NotFound(f"User with machine_id {machine_id} not found")
        before = dict(row)
        user_name = data.get("user_name", before["user_name"])
        email = data.get("email", before.get("email"))
        role = data.get("role", before["role"])
        if role not in ("admin", "requester"):
            raise ValidationError("role must be 'admin' or 'requester'")
        timestamp = now()
        conn.execute(
            """
            update users set user_name = ?, email = ?, role = ?, updated_at = ? where machine_id = ?
            """,
            (user_name, email, role, timestamp, machine_id),
        )
        after = {**before, "user_name": user_name, "email": email, "role": role, "updated_at": timestamp}
        write_audit_log(
            conn,
            action_type="update_user",
            object_type="user",
            object_id=before["user_id"],
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=before,
            after=after,
        )
        conn.commit()
    return after


def disable_user(config: AppConfig, current_user: dict, machine_id: str) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can disable users")
    if machine_id == current_user.get("machine_id"):
        raise ValidationError("Cannot disable your own account")
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()
        if not row:
            raise NotFound(f"User with machine_id {machine_id} not found")
        before = dict(row)
        timestamp = now()
        conn.execute(
            "update users set status = 'disabled', updated_at = ? where machine_id = ?",
            (timestamp, machine_id),
        )
        after = {**before, "status": "disabled", "updated_at": timestamp}
        write_audit_log(
            conn,
            action_type="disable_user",
            object_type="user",
            object_id=before["user_id"],
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=before,
            after=after,
        )
        conn.commit()
    return after
```

Add imports at top of `user_service.py`:
```python
from sc_gr_app.errors import PermissionDenied, ValidationError, NotFound
from sc_gr_app.services.audit_service import write_audit_log
```

- [ ] **Step 4: Run backend tests**

Run: `uv run pytest tests/test_user_service.py -q`
Expected: All user CRUD tests pass.

- [ ] **Step 5: Add bridge endpoints**

In `sc_gr_app/api/bridge.py`, add:

```python
def create_user(self, payload) -> dict:
    try:
        payload = self._required_payload(payload)
        current_user = self._require_current_user()
        data = _require_payload_field(payload, "data")
        from sc_gr_app.services.user_service import create_user
        return ok(create_user(self.config, current_user, data))
    except Exception as exc:
        return fail(exc)

def update_user(self, payload) -> dict:
    try:
        payload = self._required_payload(payload)
        current_user = self._require_current_user()
        machine_id = _require_payload_field(payload, "machine_id")
        data = _require_payload_field(payload, "data")
        from sc_gr_app.services.user_service import update_user
        return ok(update_user(self.config, current_user, machine_id, data))
    except Exception as exc:
        return fail(exc)

def disable_user(self, payload) -> dict:
    try:
        payload = self._required_payload(payload)
        current_user = self._require_current_user()
        machine_id = _require_payload_field(payload, "machine_id")
        from sc_gr_app.services.user_service import disable_user
        return ok(disable_user(self.config, current_user, machine_id))
    except Exception as exc:
        return fail(exc)
```

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 7: Expand renderSystem with user management section**

In `sc_gr_app/web/components/views.js`, replace the `renderSystem` function:

```javascript
function renderSystem(regions) {
  const user = state.user;
  const isAdmin = user?.role === "admin";
  const authorized = user ? "Authorized" : "Not authorized";
  const users = state.users || [];

  let userMgmtHtml = "";
  if (isAdmin) {
    userMgmtHtml = `
      <div class="user-mgmt-section" x-data="{
        showForm: false,
        editTarget: null,
        formMode: 'add',
        machineId: '',
        userName: '',
        email: '',
        role: 'requester'
      }">
        <div class="section-toolbar">
          <h3>User Management</h3>
          <button type="button" class="button primary" @click="
            showForm = true;
            formMode = 'add';
            editTarget = null;
            machineId = '';
            userName = '';
            email = '';
            role = 'requester';
          ">Add User</button>
        </div>

        <table class="data-table detail-table" style="margin-top: 10px;">
          <thead>
            <tr>
              <th>Machine ID</th>
              <th>Name</th>
              <th>Email</th>
              <th>Role</th>
              <th>Status</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            ${users.map((u) => `
              <tr class="status-row status-${escapeHtml(u.status)}">
                <td>${escapeHtml(text(u.machine_id))}</td>
                <td>${escapeHtml(text(u.user_name))}</td>
                <td>${escapeHtml(text(u.email))}</td>
                <td>${escapeHtml(text(u.role))}</td>
                <td>${statusBadge(u.status)}</td>
                <td>
                  <div class="row-actions">
                    <button type="button" class="button compact" @click="
                      showForm = true;
                      formMode = 'edit';
                      editTarget = '${escapeHtml(u.machine_id)}';
                      machineId = '${escapeHtml(u.machine_id)}';
                      userName = '${escapeHtml(text(u.user_name))}';
                      email = '${escapeHtml(text(u.email ?? ''))}';
                      role = '${escapeHtml(u.role)}';
                    ">Edit</button>
                    ${u.status === 'active' ? `
                      <button type="button" class="button compact danger" @click="
                        if (window.confirm('Disable user ${escapeHtml(text(u.user_name))}?')) {
                          window.__disableMachineId = '${escapeHtml(u.machine_id)}';
                          window.__userAction = 'disable';
                        }
                      ">Disable</button>
                    ` : ""}
                  </div>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>

        <div x-show="showForm" class="inline-user-form" @keydown.escape.window="showForm = false">
          <h4 x-text="formMode === 'add' ? 'Add User' : 'Edit User'"></h4>
          <div class="form-grid" style="margin-top: 10px;">
            <label class="form-field">
              <span>Machine ID (7-digit)</span>
              <input type="text" x-model="machineId" :readonly="formMode === 'edit'" maxlength="7" pattern="[A-Z0-9]{7}">
            </label>
            <label class="form-field">
              <span>Name</span>
              <input type="text" x-model="userName">
            </label>
            <label class="form-field">
              <span>Email</span>
              <input type="email" x-model="email">
            </label>
            <label class="form-field">
              <span>Role</span>
              <select x-model="role">
                <option value="requester">Requester</option>
                <option value="admin">Admin</option>
              </select>
            </label>
          </div>
          <div class="actions" style="margin-top: 10px;">
            <button type="button" class="button primary" @click="
              window.__userFormData = {
                mode: formMode,
                machineId: machineId,
                data: {
                  machine_id: machineId,
                  user_name: userName,
                  email: email,
                  role: role
                }
              };
              window.__userAction = formMode === 'add' ? 'create' : 'update';
            ">Save</button>
            <button type="button" class="button" @click="showForm = false">Cancel</button>
          </div>
        </div>
      </div>
    `;
  }

  regions.home.innerHTML = `
    <div class="home-intro">
      <h2>System</h2>
      <p>Current desktop identity and bridge availability are shown here for operations support.</p>
    </div>
    <div class="summary-grid">
      <div class="metric-card"><div class="metric-label">Authorization</div><div class="metric-value">${escapeHtml(authorized)}</div><div class="metric-note">${escapeHtml(state.userError ?? "Machine is mapped to an active user")}</div></div>
      <div class="metric-card"><div class="metric-label">Role</div><div class="metric-value">${escapeHtml(user?.role ?? "-")}</div><div class="metric-note">${escapeHtml(user?.user_name ?? "No active user loaded")}</div></div>
      <div class="metric-card"><div class="metric-label">Machine ID</div><div class="metric-value">${escapeHtml(user?.machine_id ?? "-")}</div><div class="metric-note">Windows user/device identity</div></div>
      <div class="metric-card"><div class="metric-label">Bridge</div><div class="metric-value">${window.pywebview?.api ? "Ready" : "Unavailable"}</div><div class="metric-note">Provided by pywebview</div></div>
    </div>
    ${userMgmtHtml}
  `;
  regions.table.innerHTML = "";

  // Poll for user actions from Alpine
  const checkActions = () => {
    if (window.__userAction) {
      const action = window.__userAction;
      const formData = window.__userFormData;
      window.__userAction = null;
      window.__userFormData = null;

      (async () => {
        try {
          if (action === "create") {
            await callApi("create_user", { data: formData.data });
          } else if (action === "update") {
            await callApi("update_user", { machine_id: formData.machineId, data: formData.data });
          } else if (action === "disable") {
            const machineId = window.__disableMachineId;
            window.__disableMachineId = null;
            await callApi("disable_user", { machine_id: machineId });
          }
          // Refresh user list and re-render
          state.users = await callApi("list_users", {});
          renderSystem(regions);
        } catch (e) {
          alert(e.message);
        }
      })();
    }
    if (document.querySelector(".user-mgmt-section")) {
      setTimeout(checkActions, 200);
    }
  };
  if (isAdmin) {
    setTimeout(checkActions, 200);
  }
}
```

- [ ] **Step 8: Verify the full flow**

Run: `uv run python -m sc_gr_app.main`
Expected:
- Login as admin → System view shows user management table with all users
- Add User → form appears → fill in → Save → user appears in table
- Edit User → form pre-fills → change fields → Save → updated
- Disable User → confirm → user status changes to disabled
- Login as requester → System view shows only metric cards, no user management

- [ ] **Step 9: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 10: Commit**

```bash
git add sc_gr_app/services/user_service.py sc_gr_app/api/bridge.py sc_gr_app/web/components/views.js tests/test_user_service.py
git commit -m "feat: add admin user management CRUD in System view with audit logging"
```

---

## Summary

All 10 tasks produce incremental, independently verifiable commits. After each task, the app should be runnable and the existing test suite should pass. Manual verification steps are listed for each UI task.
