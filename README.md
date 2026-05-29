# SC GR Management

Windows desktop application for department-side SC (Shopping Cart) budget, PO (Purchase Order) / vendor, and GR (Goods Receipt) management. Built for Audi C/EV-L.

The app tracks SCs, POs, vendors, and GRs locally; actual financial approval happens in an external system. Core domain rule: **SC is the budget source** — PO allocates SC funds to vendors, GR draws from PO funds.

## Architecture

```
Python 3.11 + pywebview + SQLite          ← Desktop shell / backend
Vue 3 + Vite + Element Plus               ← Frontend (built to sc_gr_app/web/)
PyInstaller + Inno Setup                  ← Windows installer packaging
```

- **No app server**: all business logic runs locally on the client.
- **Database**: shared-folder SQLite (`data/sc_gr.sqlite3`) with rollback journal (not WAL).
- **Concurrency**: file-based lease locks under `data/locks/` for write operations, using a `sc:{id}` → `BEGIN IMMEDIATE` → validate → write → audit → commit pattern.
- **Frontend**: Vue 3 SPA built with Vite, output to `sc_gr_app/web/`; pywebview loads it via `WebView2`.
- **Desktop features**: system tray, single-instance lock, WebView2 runtime, dev-mode hot-reload for the Vue frontend.

## Project structure

```
sc_gr_app/
  main.py               # Entry point (tray, window, single-instance)
  app_shell.py          # Pywebview window + JS API bridge registration
  config.py             # AppConfig dataclass (db_path, lock_dir, data_dir)
  identity.py           # Machine identity from Windows username
  rbac.py               # Role-based access helpers
  errors.py             # Exception hierarchy
  db/
    connection.py       # SQLite connect with PRAGMA settings
    migrations.py       # Schema versioning, runs on startup
  api/
    bridge.py           # ApiBridge — every method is a JS-callable endpoint
    schemas.py          # ok() / fail() response envelope
  services/
    user_service.py     # User CRUD, seed default admin
    sc_service.py       # SC lifecycle: draft → submit → approve/deny/close
    po_service.py       # PO lifecycle with SC budget allocation
    gr_service.py       # GR create/approve/cancel, draws from PO
    vendor_service.py   # Vendor CRUD
    budget_service.py   # Derived budget math (Decimal-based)
    query_service.py    # Unified search across all entities
    audit_service.py    # Audit log writes with before/after snapshots
    lock_service.py     # File-based lease lock with TTL and heartbeat
  web/                  # Built Vue frontend (served by pywebview)
frontend/
  src/
    views/              # Vue views: Home, Lists (SC/PO/GR/Vendor), Detail, System, Logs, Login
    components/         # Reusable components: tables, forms, filters, status badges
    composables/        # Composition API hooks: useSc, usePo, useGr, useVendor, useUser
    api/bridge.js       # callApi() — thin wrapper over window.pywebview.api
    router/index.js     # Vue Router config
packaging/
  app.spec              # PyInstaller spec
  setup.iss             # Inno Setup installer script
  build.ps1             # Build script (sync → test → pyinstaller)
tests/                  # pytest test suite with real SQLite per test
```

## Domain model

```
SC (Shopping Cart) ──< PO (Purchase Order) ──< GR (Goods Receipt)
     │                       │                      │
     │ budget source         │ allocates SC funds    │ draws from PO
     │                       │ to vendors           │ confirms delivery
```

- **SC status flow**: `draft` → `pending` → `approved` / `denied` / `closed`
- **PO status flow**: `draft` → `pending` → `approved` / `denied`
- **GR status flow**: `pending` → `approved` / `cancelled`
- **SC draft workflow**: `create_sc_draft` creates a `draft` SC with minimal fields; `submit_sc` transitions to `pending` with full field validation — lets requesters save partial work.
- **Budget computation**: all budget numbers are derived from GR records in real time using `Decimal` arithmetic (no redundancy, no float errors). SC budget = `sc_amount - pending GR estimated_amount - approved GR con_value`. PO budget = `po_amount - pending GR estimated_amount - approved GR con_value`.
- **SC visibility**: admins see all non-draft SCs; requesters see own SCs (including drafts) + all non-draft SCs they own. Draft SCs are invisible to everyone except the owning requester.

## Write safety

Every SC/PO/GR mutation follows this pattern:

1. Acquire `LeaseLock` for `sc:{sc_id}`
2. `connect()` + `BEGIN IMMEDIATE`
3. Re-read current state (never trust stale UI data)
4. Validate business rules + permissions
5. Execute write
6. `write_audit_log()` with before/after snapshots
7. `COMMIT` (rollback on any error)
8. Release lock

## Development

**Prerequisites**: Python 3.11, [uv](https://docs.astral.sh/uv/), Node.js 18+ (for frontend dev).

```powershell
# Backend — install dependencies
uv sync --all-groups

# Frontend — install dependencies
cd frontend && npm install

# Run all tests
uv run pytest -q

# Run a single test file
uv run pytest tests/test_sc_service.py -q

# Run a single test
uv run pytest tests/test_sc_service.py::test_specific_name -q

# Start desktop app in dev mode (frontend hot-reload on localhost:5173)
uv run python -m sc_gr_app.main --dev

# Start desktop app (production mode, uses built frontend)
uv run python -m sc_gr_app.main
```

### Frontend development

```powershell
cd frontend
npm run dev       # Start Vite dev server at localhost:5173
npm run build     # Build to ../sc_gr_app/web/
```

When running the desktop app with `--dev`, pywebview loads from `http://localhost:5173` and you get hot module replacement. Without `--dev`, it loads from the built files in `sc_gr_app/web/`.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SC_GR_DATA_DIR` | Override data directory (DB + locks) | `./data` relative to executable |

## Windows installer build

```powershell
powershell -ExecutionPolicy Bypass -File packaging/build.ps1
```

This runs `uv sync`, `pytest`, and `pyinstaller` in sequence. After the build, run the Inno Setup Compiler on `packaging/setup.iss` to produce `dist/installer/SC-GR-Management-2.0.0-Setup.exe`.

## Operations

- Database and lock files live under the data directory (`./data/` by default, or `SC_GR_DATA_DIR` if set).
- If stale lock files remain after a crash, delete only expired `.lock` files after confirming the app is not running. Do not remove active lock files from a running session.
- For shared-folder deployment: set `SC_GR_DATA_DIR` to a UNC path accessible by all clients in the department.

## Testing

Tests use `pytest` with an `app_config` fixture that creates an isolated `tmp_path` per test — each test gets its own SQLite database. No mocking of the database; tests exercise real SQLite. The `migrate()` function is called in individual test files when needed.

Test pattern: create users via direct INSERT, call service functions with `app_config` + `current_user` dict, assert on returned data and database state.
