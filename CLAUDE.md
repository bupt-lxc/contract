# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

Windows desktop app (Python 3.11 + pywebview + SQLite) for department-side SC budget, PO/vendor, and GR management. Vue 3 + Vite + Element Plus frontend. No app server — all logic runs locally on the client against a shared-folder SQLite database.

## Branching rules (CRITICAL)

> **NEVER commit directly to `main`.** This rule applies to both Claude and the user.

- **New feature** → branch from `main` as `feat/<name>`, merge back to `main` after completion
- **Bug fix** → branch from `main` as `fix/<name>`, merge back to `main` after completion
- **One feature per branch** — different features go to different branches. Do NOT pile unrelated features onto the same branch.
- Before starting ANY code change, verify you are NOT on `main` (`git branch --show-current`)
- If on `main` when work is requested, immediately switch to a new feature/fix branch
- Only merge to `main` after the feature or fix is complete and verified
- Do NOT push to remote or create PRs unless the user explicitly commands it

## Commands

```powershell
# Backend dependencies
uv sync --all-groups

# Frontend dependencies
cd frontend && npm install

# Run all tests (pytest, real SQLite per test — no mocks)
uv run pytest -q

# Run single test file
uv run pytest tests/test_sc_service.py -q

# Run single test
uv run pytest tests/test_sc_service.py::test_specific_name -q

# Desktop app in dev mode (frontend hot-reload from localhost:5173)
uv run python -m sc_gr_app.main --dev

# Desktop app in production mode (uses built frontend from sc_gr_app/web/)
uv run python -m sc_gr_app.main

# Frontend dev server (standalone)
cd frontend && npm run dev

# Frontend build
cd frontend && npm run build

# Notification script (runs on dedicated always-on machine)
uv run python -m sc_gr_app.notification                          # poll every 5 min
uv run python -m sc_gr_app.notification --run-once               # one cycle + exit
uv run python -m sc_gr_app.notification --draft --poll-interval 60  # draft mode

# Windows installer build
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

## Architecture patterns

### JS-to-Python bridge

The frontend calls Python via `window.pywebview.api.<method>(payload)`. Every method on `ApiBridge` (`sc_gr_app/api/bridge.py`) is automatically exposed to JS. The convention:

- Every bridge method wraps its body in `try/except Exception as exc: return fail(exc)`.
- On success, return `ok(data)`.
- `ok()` / `fail()` come from `api/schemas.py` and produce the `{ok, data/error}` envelope.
- On the frontend side, `callApi(method, payload)` in `frontend/src/api/bridge.js` unpacks the envelope — throws `ApiError` on failure, returns `data` on success.
- The `_require_current_user()` helper on the bridge resolves the Windows username (7-digit machine ID) to a user row. Every authenticated endpoint calls this first.

### Write safety pattern (lock → validate → write → audit)

Every SC/PO/GR mutation in `services/` follows this sequence:

1. Acquire `LeaseLock` for `sc:{sc_id}` (file-based lease lock with TTL + heartbeat in `data/locks/`)
2. `connect()` + `BEGIN IMMEDIATE`
3. Re-read current DB state (never trust stale UI data)
4. Validate business rules + permissions (RBAC via `rbac.py`)
5. Execute write
6. `write_audit_log()` with before/after JSON snapshots
7. `COMMIT` (rollback on any error)
8. Release lock

The lock-service (`services/lock_service.py`) uses `os.open(O_CREAT | O_EXCL)` for atomic file creation on shared drives. Stale locks (past `expires_at`) are detected and can be cleaned.

### Budget computation

All budget numbers are **derived in real time from GR records** using `Decimal` arithmetic — nothing is stored redundantly. `services/budget_service.py` provides `compute_sc_budget()` and `compute_po_budget()`. Key formulas:

- SC available = `sc_amount - sum(pending GR estimated_amount) - sum(approved GR con_value)`
- PO open = `po_amount - sum(pending GR estimated_amount) - sum(approved GR con_value)`

### Notification architecture

Two-part system (see `services/notification_service.py` + `sc_gr_app/notification/`):

- **Desktop clients** write queue entries to `notification_queue` table inside existing DB transactions. They never send email.
- **Notification script** (`python -m sc_gr_app.notification`) runs on a dedicated always-on Windows machine with Outlook. It polls the queue, sends via Outlook COM, retries failures, and runs daily threshold checks.
- Recipient resolution: keywords `requester`, `actor`, `notify.admin_recipients` in to/cc rules are resolved to user IDs then email addresses at send time.
- Threshold dedup via `notification_sent_threshold` table — each condition fires at most once.

### Permission model

`rbac.py` provides three helpers used throughout services:

- `require_admin(user)` — admin-only operations
- `require_requester_or_admin(user)` — any authenticated role
- `can_edit_sc(user, requester_id)` — admin or SC owner

Permissions are checked at the Python API layer (bridge), never trusted from the frontend alone.

### DB conventions

- `db/connection.py` — single `connect()` function: sets `row_factory = sqlite3.Row`, `PRAGMA foreign_keys = ON`, `PRAGMA journal_mode = DELETE` (rollback journal, not WAL), configurable `busy_timeout`.
- `db/migrations.py` — schema versioning via `schema_migrations` table; `migrate()` runs on every startup.
- Tests use the `app_config` fixture (`tests/conftest.py`) which creates an isolated `tmp_path` with its own SQLite DB. No mocking of the database layer.
- Service functions accept `config: AppConfig` + `current_user: dict` as their first two positional args (convention).

### Frontend structure

- **Views** (`views/`) — page-level components, one per route
- **Composables** (`composables/`) — Vue Composition API hooks (`useSc`, `usePo`, `useGr`, `useVendor`, `useUser`, `useNotification`), each holds reactive state and calls `callApi()`
- **Layout components** (`components/layout/`) — `SideNav`, `AppLayout`
- Router uses hash history (`createWebHashHistory`) since pywebview serves from `file://` in production

### Identity

User identity comes from `os.getlogin()` (the Windows username, a 7-digit machine ID). `identity.py` → `get_7_digit_id()`. The `users` table maps machine_id → user record with role (`admin` / `requester`).

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SC_GR_DATA_DIR` | Override data directory (DB + locks) | Shared UNC path |
| `SC_GR_DEV` | Dev mode: local AppData dir, auto-create user, enable dev tools | (unset) |
