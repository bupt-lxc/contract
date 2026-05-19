# SC GR Management Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Windows desktop SC budget, PO/vendor, and GR management application using Python, pywebview, and a shared-folder SQLite database.

**Architecture:** The application is a single desktop app with a pywebview shell, static HTML/CSS/JS frontend, Python API layer, service layer, SQLite repository layer, and shared-folder lease locks. Reads are lock-free; writes use `sc:{sc_id}` or `system` lease locks plus a short `db-write-gate` and SQLite `BEGIN IMMEDIATE`.

**Tech Stack:** Python 3.11+, uv-managed environment and lockfile, pywebview, SQLite, pytest, vanilla HTML/CSS/JS, PyInstaller.

---

## Plan Granularity Note

This is the master implementation plan for the whole application. It locks architecture, file boundaries, development order, data contracts, and verification gates.

Before executing a large task that creates several service or frontend files, expand that task into a task-level coding plan with exact function bodies and tests. The highest-risk tasks that must be expanded before coding are:

- Task 6: SC, vendor, PO, and GR services.
- Task 7: query service.
- Task 9: frontend UI implementation.
- Task 10: packaging.

Do not treat summary bullets in those tasks as permission to improvise behavior. The business rules in this plan and in `é¡¹ç›®è¯´æ˜Ž.md` are binding.

## Product Decisions To Preserve

- No app server.
- Business logic runs on the client.
- Database is a SQLite file in a shared folder.
- Use rollback journal, not WAL.
- Read operations do not take app-level locks.
- Write operations use lease locks and short SQLite transactions.
- Roles are `admin` and `requester`.
- Code/schema naming uses `vendor`, not supplier.
- Python interpreter, dependency resolution, lockfile, test execution, and packaging commands are managed by `uv`. Do not use `pip install` or bare `python`/`pytest` commands in project documentation or scripts; use `uv sync`, `uv add`, and `uv run ...`.
- User/device identity uses the same rule as `get_7_digit_id.py`: first call `os.getlogin().strip()`, and if that fails or returns an empty string, fall back to `os.getenv("USERNAME", "").strip()`. Preserve the returned string after `strip()` only; do not uppercase, truncate, pad, apply an app-specific override environment variable, or derive identity from hostname. The schema keeps the column name `machine_id`, but its value is this Windows user/device ID.
- SC service period is estimated only and does not block GR or trigger reminders.
- PO `contract_to` is the date that needs later email reminder support.
- GR links to PO by `po_id`; SC is reached through `pos.sc_id`.
- GR does not have `reason`, `finance_reference_no`, `actual_amount`, or `sc_id`.
- GR approved amount field is `con_value`.
- OPEN PO is derived as `open_po_amount`; do not store it.
- No dark mode. UI uses a bright, clean, work-focused visual direction.
- Frontend implementation must use the `frontend-design` skill before UI code is written.

## File Structure

Create this structure:

```text
.python-version
pyproject.toml
uv.lock
sc_gr_app/
  __init__.py
  main.py
  app_shell.py
  config.py
  errors.py
  identity.py
  rbac.py
  api/
    __init__.py
    bridge.py
    schemas.py
  db/
    __init__.py
    connection.py
    migrations.py
    schema.sql
    repositories.py
  services/
    __init__.py
    audit_service.py
    budget_service.py
    gr_service.py
    lock_service.py
    po_service.py
    query_service.py
    sc_service.py
    user_service.py
    vendor_service.py
  web/
    index.html
    styles.css
    app.js
    components/
      api.js
      format.js
      state.js
      tables.js
      views.js
tests/
  conftest.py
  test_budget_service.py
  test_identity.py
  test_lock_service.py
  test_migrations.py
  test_query_service.py
  test_rbac.py
  test_sc_po_gr_flow.py
  test_vendor_service.py
packaging/
  build.ps1
  app.spec
README.md
```

Responsibilities:

- `main.py`: application entry point.
- `app_shell.py`: starts pywebview and exposes the Python API bridge.
- `config.py`: database path, lock directory path, app settings.
- `errors.py`: domain errors returned to frontend.
- `identity.py`: reads the current Windows user/device ID using the `get_7_digit_id.py` rule and maps it to a user.
- `.python-version`: pins the uv-managed Python interpreter to 3.11.
- `pyproject.toml`: declares the uv project metadata, runtime dependency `pywebview`, and dev dependencies `pytest` and `pyinstaller`.
- `uv.lock`: locks the resolved dependency graph.
- `rbac.py`: central role checks.
- `api/bridge.py`: methods callable from JavaScript.
- `api/schemas.py`: request/response normalization and validation helpers.
- `db/connection.py`: SQLite connection factory and pragmas.
- `db/migrations.py`: schema version management.
- `db/schema.sql`: initial schema.
- `db/repositories.py`: focused SQL helpers.
- `services/*`: business logic and transactions.
- `web/*`: bright frontend UI.
- `tests/*`: unit and integration tests.
- `packaging/*`: Windows executable build support.

## Implementation Tasks

### Task 1: Project Skeleton And Test Harness

**Files:**
- Create: `.python-version`
- Create: `pyproject.toml`
- Create: `uv.lock`
- Create: `sc_gr_app/__init__.py`
- Create: `sc_gr_app/main.py`
- Create: `sc_gr_app/config.py`
- Create: `sc_gr_app/errors.py`
- Create: `tests/conftest.py`
- Create: `README.md`

- [ ] **Step 1: Initialize uv project files**

Run:

```powershell
uv init --bare --no-readme --vcs none --name sc-gr-management
uv python pin 3.11
uv add pywebview
uv add --dev pytest pyinstaller
uv sync --all-groups
```

Expected:

- `.python-version` contains `3.11`.
- `pyproject.toml` contains `requires-python = ">=3.11"`.
- `pyproject.toml` has runtime dependency `pywebview`.
- `pyproject.toml` has dev dependencies `pytest` and `pyinstaller`.
- `uv.lock` exists.

- [ ] **Step 2: Create base package files**

Create empty `sc_gr_app/__init__.py`.

Create `sc_gr_app/errors.py`:

```python
class AppError(Exception):
    code = "APP_ERROR"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ValidationError(AppError):
    code = "VALIDATION_ERROR"


class PermissionDenied(AppError):
    code = "PERMISSION_DENIED"


class NotFound(AppError):
    code = "NOT_FOUND"


class LockError(AppError):
    code = "LOCK_ERROR"


class ConflictError(AppError):
    code = "CONFLICT_ERROR"
```

- [ ] **Step 3: Add config**

Create `sc_gr_app/config.py`:

```python
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppConfig:
    db_path: Path
    lock_dir: Path
    busy_timeout_ms: int = 5000


def default_config(base_dir: Path | None = None) -> AppConfig:
    root = base_dir or Path.cwd()
    data_dir = root / "data"
    return AppConfig(
        db_path=data_dir / "sc_gr.sqlite3",
        lock_dir=data_dir / "locks",
    )
```

- [ ] **Step 4: Add pytest fixtures**

Create `tests/conftest.py`:

```python
from pathlib import Path

import pytest

from sc_gr_app.config import AppConfig


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        db_path=tmp_path / "test.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )
```

- [ ] **Step 5: Add app entry placeholder**

Create `sc_gr_app/main.py`:

```python
from sc_gr_app.app_shell import run_app


def main() -> None:
    run_app()


if __name__ == "__main__":
    main()
```

This will fail until `app_shell.py` is added in a later task.

- [ ] **Step 6: Run tests**

Run: `uv run pytest -q`

Expected: collection succeeds if pytest is installed; no test files yet.

### Task 2: SQLite Connection And Schema Migration

**Files:**
- Create: `sc_gr_app/db/__init__.py`
- Create: `sc_gr_app/db/connection.py`
- Create: `sc_gr_app/db/schema.sql`
- Create: `sc_gr_app/db/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write migration test**

Create `tests/test_migrations.py`:

```python
import sqlite3

from sc_gr_app.db.migrations import migrate


def test_migration_creates_core_tables(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }

    assert {
        "schema_migrations",
        "users",
        "sc_records",
        "vendors",
        "pos",
        "gr_requests",
        "audit_logs",
        "app_settings",
    }.issubset(tables)
```

- [ ] **Step 2: Run failing test**

Run: `uv run pytest tests/test_migrations.py -q`

Expected: FAIL because migration module does not exist.

- [ ] **Step 3: Create schema**

Create `sc_gr_app/db/schema.sql`:

```sql
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version INTEGER PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  machine_id TEXT NOT NULL UNIQUE,
  user_name TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('admin', 'requester')),
  email TEXT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sc_records (
  sc_id TEXT PRIMARY KEY,
  sc_no TEXT,
  requester_id TEXT NOT NULL REFERENCES users(user_id),
  request_type TEXT NOT NULL CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
  cost_center INTEGER NOT NULL,
  sc_amount REAL NOT NULL CHECK (sc_amount > 0),
  service_period_start TEXT NOT NULL,
  service_period_end TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'closed')),
  description TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  approved_by TEXT REFERENCES users(user_id),
  approved_at TEXT,
  closed_at TEXT
);

CREATE TABLE IF NOT EXISTS vendors (
  vendor_id TEXT PRIMARY KEY,
  vendor_name TEXT NOT NULL,
  ksrm_vendor_code TEXT,
  contact_person TEXT,
  phone TEXT,
  service_scope TEXT NOT NULL CHECK (service_scope IN (
    'Transportation',
    'engineering Service',
    'Equipment',
    'Parts',
    'Driver',
    'Test car rental',
    'General Service',
    'Dealers',
    'Import&Export&cusoms clearance',
    'Insurance',
    'Harness',
    'Maintenance',
    'Security',
    'Testing support',
    'Others'
  )),
  email TEXT,
  description TEXT,
  inquiry_history TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pos (
  po_id TEXT PRIMARY KEY,
  sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
  vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
  po_no TEXT,
  po_amount REAL NOT NULL CHECK (po_amount > 0),
  status TEXT NOT NULL CHECK (status IN ('po_pending', 'po_approved', 'finished')),
  contract_from TEXT,
  contract_to TEXT,
  contract_no TEXT,
  payment_frequency TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS gr_requests (
  gr_id TEXT PRIMARY KEY,
  po_id TEXT NOT NULL REFERENCES pos(po_id),
  requester_id TEXT NOT NULL REFERENCES users(user_id),
  estimated_amount REAL NOT NULL CHECK (estimated_amount > 0),
  con_value REAL CHECK (con_value >= 0),
  status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'cancelled')),
  remark TEXT,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  approved_by TEXT REFERENCES users(user_id),
  approved_at TEXT,
  cancelled_by TEXT REFERENCES users(user_id),
  cancelled_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_logs (
  log_id TEXT PRIMARY KEY,
  action_type TEXT NOT NULL,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  sc_id TEXT,
  operator_id TEXT NOT NULL,
  machine_id TEXT NOT NULL,
  before_json TEXT,
  after_json TEXT,
  operation_mode TEXT NOT NULL DEFAULT 'normal',
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_settings (
  setting_key TEXT PRIMARY KEY,
  setting_value TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id);
CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status);
CREATE INDEX IF NOT EXISTS idx_vendors_name ON vendors(vendor_name);
CREATE INDEX IF NOT EXISTS idx_pos_sc ON pos(sc_id);
CREATE INDEX IF NOT EXISTS idx_pos_vendor ON pos(vendor_id);
CREATE INDEX IF NOT EXISTS idx_pos_status ON pos(status);
CREATE INDEX IF NOT EXISTS idx_gr_po ON gr_requests(po_id);
CREATE INDEX IF NOT EXISTS idx_gr_status ON gr_requests(status);
CREATE INDEX IF NOT EXISTS idx_audit_sc ON audit_logs(sc_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_logs(created_at);
```

- [ ] **Step 4: Implement connection and migration**

Create `sc_gr_app/db/__init__.py` empty.

Create `sc_gr_app/db/connection.py`:

```python
import sqlite3
from pathlib import Path

from sc_gr_app.config import AppConfig


def connect(config: AppConfig) -> sqlite3.Connection:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = DELETE")
    conn.execute(f"PRAGMA busy_timeout = {config.busy_timeout_ms}")
    return conn
```

Create `sc_gr_app/db/migrations.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 1


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def migrate(config: AppConfig) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    schema_sql = schema_path.read_text(encoding="utf-8")

    with connect(config) as conn:
        conn.executescript(schema_sql)
        exists = conn.execute(
            "select 1 from schema_migrations where version = ?",
            (SCHEMA_VERSION,),
        ).fetchone()
        if not exists:
            conn.execute(
                "insert into schema_migrations(version, applied_at) values (?, ?)",
                (SCHEMA_VERSION, utc_now()),
            )
        conn.commit()
```

- [ ] **Step 5: Run migration test**

Run: `uv run pytest tests/test_migrations.py -q`

Expected: PASS.

### Task 3: Identity, RBAC, And Seed Admin

**Files:**
- Create: `sc_gr_app/identity.py`
- Create: `sc_gr_app/rbac.py`
- Create: `sc_gr_app/services/user_service.py`
- Test: `tests/test_identity.py`
- Test: `tests/test_rbac.py`

- [ ] **Step 1: Write identity and RBAC tests**

Create `tests/test_identity.py`:

```python
import os

import pytest

from sc_gr_app.identity import get_7_digit_id, get_machine_id


def test_get_7_digit_id_prefers_os_getlogin(monkeypatch):
    monkeypatch.setattr(os, "getlogin", lambda: " V2SE7PP ")
    monkeypatch.setenv("USERNAME", "FALLBACK")

    assert get_7_digit_id() == "V2SE7PP"
    assert get_machine_id() == "V2SE7PP"


def test_get_7_digit_id_falls_back_to_username(monkeypatch):
    def raise_getlogin():
        raise OSError("no login")

    monkeypatch.setattr(os, "getlogin", raise_getlogin)
    monkeypatch.setenv("USERNAME", " V2SE7PP ")

    assert get_7_digit_id() == "V2SE7PP"


def test_get_7_digit_id_returns_empty_string_when_unavailable(monkeypatch):
    def raise_getlogin():
        raise OSError("no login")

    monkeypatch.setattr(os, "getlogin", raise_getlogin)
    monkeypatch.delenv("USERNAME", raising=False)

    assert get_7_digit_id() == ""
```

Create `tests/test_rbac.py`:

```python
import pytest

from sc_gr_app.errors import PermissionDenied
from sc_gr_app.rbac import require_admin, require_requester_or_admin


def test_require_admin_allows_admin():
    require_admin({"role": "admin"})


def test_require_admin_rejects_requester():
    with pytest.raises(PermissionDenied):
        require_admin({"role": "requester"})


def test_requester_or_admin_allows_both_roles():
    require_requester_or_admin({"role": "admin"})
    require_requester_or_admin({"role": "requester"})
```

- [ ] **Step 2: Run failing tests**

Run: `uv run pytest tests/test_identity.py tests/test_rbac.py -q`

Expected: FAIL because `identity.py` and `rbac.py` do not exist.

- [ ] **Step 3: Implement RBAC**

Create `sc_gr_app/rbac.py`:

```python
from sc_gr_app.errors import PermissionDenied


def require_admin(user: dict) -> None:
    if user.get("role") != "admin":
        raise PermissionDenied("Admin permission required")


def require_requester_or_admin(user: dict) -> None:
    if user.get("role") not in {"admin", "requester"}:
        raise PermissionDenied("Authorized user required")


def can_edit_sc(user: dict, requester_id: str) -> bool:
    return user.get("role") == "admin" or user.get("user_id") == requester_id
```

Create `sc_gr_app/identity.py`:

```python
import os


def get_7_digit_id() -> str:
    try:
        value = os.getlogin().strip()
        if value:
            return value
    except Exception:
        pass
    return os.getenv("USERNAME", "").strip()


def get_machine_id() -> str:
    return get_7_digit_id()
```

Create `sc_gr_app/services/user_service.py`:

```python
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import PermissionDenied
from sc_gr_app.identity import get_7_digit_id


DEFAULT_ADMIN_USER_ID = "U-ADMIN"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_default_admin(config: AppConfig) -> None:
    machine_id = get_7_digit_id()
    if not machine_id:
        raise PermissionDenied("Failed to get Windows user ID")

    timestamp = now()
    with connect(config) as conn:
        existing = conn.execute(
            "select 1 from users where machine_id = ?",
            (machine_id,),
        ).fetchone()
        if not existing:
            conn.execute(
                """
                insert into users(user_id, machine_id, user_name, role, email, status, created_at, updated_at)
                values (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    DEFAULT_ADMIN_USER_ID,
                    machine_id,
                    "Default Admin",
                    "admin",
                    None,
                    "active",
                    timestamp,
                    timestamp,
                ),
            )
        conn.commit()


def get_user_by_machine_id(config: AppConfig, machine_id: str) -> dict:
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()
    if not row:
        raise PermissionDenied("This machine is not authorized")
    return dict(row)
```

- [ ] **Step 4: Run identity and RBAC tests**

Run: `uv run pytest tests/test_identity.py tests/test_rbac.py -q`

Expected: PASS.

### Task 4: Lease Lock Service

**Files:**
- Create: `sc_gr_app/services/lock_service.py`
- Test: `tests/test_lock_service.py`

- [ ] **Step 1: Write lock tests**

Create `tests/test_lock_service.py`:

```python
import pytest

from sc_gr_app.errors import LockError
from sc_gr_app.services.lock_service import LeaseLock


def test_lease_lock_blocks_second_owner(app_config):
    first = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=60)
    second = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE2", ttl_seconds=60)

    with first:
        with pytest.raises(LockError):
            second.acquire()


def test_stale_lock_can_be_replaced(app_config):
    first = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE1", ttl_seconds=-1)
    second = LeaseLock(app_config.lock_dir, "sc:SC001", "MACHINE2", ttl_seconds=60)

    first.acquire()
    second.acquire()

    second.release()
```

- [ ] **Step 2: Run failing lock tests**

Run: `uv run pytest tests/test_lock_service.py -q`

Expected: FAIL because lock service does not exist.

- [ ] **Step 3: Implement lease lock**

Create `sc_gr_app/services/lock_service.py`:

```python
import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sc_gr_app.errors import LockError


def now() -> datetime:
    return datetime.now(timezone.utc)


def encode_name(name: str) -> str:
    return name.replace(":", "__") + ".lock"


class LeaseLock:
    def __init__(self, lock_dir: Path, name: str, owner: str, ttl_seconds: int = 30):
        self.lock_dir = lock_dir
        self.name = name
        self.owner = owner
        self.ttl_seconds = ttl_seconds
        self.token = str(uuid.uuid4())
        self.path = lock_dir / encode_name(name)

    def acquire(self) -> None:
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self._is_stale():
            raise LockError(f"Lock is busy: {self.name}")

        payload = {
            "name": self.name,
            "owner": self.owner,
            "token": self.token,
            "acquired_at": now().isoformat(),
            "heartbeat_at": now().isoformat(),
            "expires_at": (now() + timedelta(seconds=self.ttl_seconds)).isoformat(),
        }
        temp_path = self.path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, self.path)

    def release(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return
        if payload.get("token") == self.token:
            self.path.unlink(missing_ok=True)

    def _is_stale(self) -> bool:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            expires_at = datetime.fromisoformat(payload["expires_at"])
        except (json.JSONDecodeError, KeyError, ValueError):
            return True
        return expires_at <= now()

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
```

- [ ] **Step 4: Run lock tests**

Run: `uv run pytest tests/test_lock_service.py -q`

Expected: PASS.

### Task 5: Audit And Budget Services

**Files:**
- Create: `sc_gr_app/services/audit_service.py`
- Create: `sc_gr_app/services/budget_service.py`
- Test: `tests/test_budget_service.py`

- [ ] **Step 1: Write budget tests**

Create `tests/test_budget_service.py`:

```python
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.budget_service import compute_sc_budget, compute_po_budget


def seed_budget_data(conn):
    conn.execute(
        "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
        ("U1", "M1", "Requester", "requester", None, "active", "now", "now"),
    )
    conn.execute(
        """
        insert into sc_records(sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
        service_period_start, service_period_end, status, description, created_by, created_at, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("SC1", "SCNO1", "U1", "service", 1001, 1000, "2026-01-01", "2026-12-31", "approved", None, "U1", "now", "now"),
    )
    conn.execute(
        """
        insert into vendors(vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        values (?, ?, ?, ?, ?, ?)
        """,
        ("V1", "Vendor", "General Service", "U1", "now", "now"),
    )
    conn.execute(
        """
        insert into pos(po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("PO1", "SC1", "V1", "PO001", 800, "po_approved", "now", "now"),
    )
    conn.execute(
        """
        insert into gr_requests(gr_id, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("GR1", "PO1", "U1", 100, None, "pending", "U1", "now"),
    )
    conn.execute(
        """
        insert into gr_requests(gr_id, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at, approved_by, approved_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        ("GR2", "PO1", "U1", 200, 150, "approved", "U1", "now", "U1", "now"),
    )
    conn.commit()


def test_budget_derives_sc_and_open_po(app_config):
    migrate(app_config)
    from sc_gr_app.db.connection import connect

    with connect(app_config) as conn:
        seed_budget_data(conn)

    sc_budget = compute_sc_budget(app_config, "SC1")
    po_budget = compute_po_budget(app_config, "PO1")

    assert sc_budget["sc_pending_total"] == 100
    assert sc_budget["sc_con_value_total"] == 150
    assert sc_budget["sc_available_amount"] == 750
    assert sc_budget["allocated_po_amount"] == 800
    assert sc_budget["unallocated_sc_amount"] == 200
    assert po_budget["open_po_amount"] == 550
```

- [ ] **Step 2: Run failing budget test**

Run: `uv run pytest tests/test_budget_service.py -q`

Expected: FAIL because budget service does not exist.

- [ ] **Step 3: Implement audit and budget services**

Create `sc_gr_app/services/audit_service.py`:

```python
import json
import uuid
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_audit_log(
    conn,
    *,
    action_type: str,
    object_type: str,
    object_id: str,
    sc_id: str | None,
    operator_id: str,
    machine_id: str,
    before: dict | None,
    after: dict | None,
    operation_mode: str = "normal",
) -> None:
    conn.execute(
        """
        insert into audit_logs(log_id, action_type, object_type, object_id, sc_id, operator_id,
        machine_id, before_json, after_json, operation_mode, created_at)
        values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid.uuid4()),
            action_type,
            object_type,
            object_id,
            sc_id,
            operator_id,
            machine_id,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            operation_mode,
            utc_now(),
        ),
    )
```

Create `sc_gr_app/services/budget_service.py`:

```python
from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import NotFound


def compute_sc_budget(config: AppConfig, sc_id: str) -> dict:
    with connect(config) as conn:
        sc = conn.execute("select sc_amount from sc_records where sc_id = ?", (sc_id,)).fetchone()
        if not sc:
            raise NotFound(f"SC not found: {sc_id}")
        row = conn.execute(
            """
            select
              coalesce(sum(case when gr.status = 'pending' then gr.estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when gr.status = 'approved' then gr.con_value else 0 end), 0) as con_value_total
            from pos po
            left join gr_requests gr on gr.po_id = po.po_id
            where po.sc_id = ?
            """,
            (sc_id,),
        ).fetchone()
        allocated = conn.execute(
            "select coalesce(sum(po_amount), 0) from pos where sc_id = ?",
            (sc_id,),
        ).fetchone()[0]

    pending_total = float(row["pending_total"])
    con_value_total = float(row["con_value_total"])
    sc_amount = float(sc["sc_amount"])
    allocated_po_amount = float(allocated)
    return {
        "sc_amount": sc_amount,
        "sc_pending_total": pending_total,
        "sc_con_value_total": con_value_total,
        "sc_available_amount": sc_amount - pending_total - con_value_total,
        "allocated_po_amount": allocated_po_amount,
        "unallocated_sc_amount": sc_amount - allocated_po_amount,
    }


def compute_po_budget(config: AppConfig, po_id: str) -> dict:
    with connect(config) as conn:
        po = conn.execute("select po_amount from pos where po_id = ?", (po_id,)).fetchone()
        if not po:
            raise NotFound(f"PO not found: {po_id}")
        row = conn.execute(
            """
            select
              coalesce(sum(case when status = 'pending' then estimated_amount else 0 end), 0) as pending_total,
              coalesce(sum(case when status = 'approved' then con_value else 0 end), 0) as con_value_total
            from gr_requests
            where po_id = ?
            """,
            (po_id,),
        ).fetchone()
    po_amount = float(po["po_amount"])
    pending_total = float(row["pending_total"])
    con_value_total = float(row["con_value_total"])
    return {
        "po_amount": po_amount,
        "po_pending_total": pending_total,
        "po_con_value_total": con_value_total,
        "open_po_amount": po_amount - pending_total - con_value_total,
    }
```

- [ ] **Step 4: Run budget tests**

Run: `uv run pytest tests/test_budget_service.py -q`

Expected: PASS.

### Task 6: SC, Vendor, PO, And GR Services

**Files:**
- Create: `sc_gr_app/services/sc_service.py`
- Create: `sc_gr_app/services/vendor_service.py`
- Create: `sc_gr_app/services/po_service.py`
- Create: `sc_gr_app/services/gr_service.py`
- Test: `tests/test_sc_po_gr_flow.py`
- Test: `tests/test_vendor_service.py`

- [ ] **Step 1: Write vendor service test**

Create `tests/test_vendor_service.py`:

```python
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.vendor_service import create_vendor, search_vendors


def test_create_and_search_vendor(app_config):
    migrate(app_config)
    from sc_gr_app.db.connection import connect

    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            ("U1", "M1", "Requester", "requester", None, "active", "now", "now"),
        )
        conn.commit()

    create_vendor(
        app_config,
        current_user={"user_id": "U1", "role": "requester", "machine_id": "M1"},
        data={
            "vendor_id": "V1",
            "vendor_name": "Alpha Logistics",
            "ksrm_vendor_code": "K001",
            "service_scope": "Transportation",
        },
    )

    results = search_vendors(app_config, text="alpha")
    assert results[0]["vendor_name"] == "Alpha Logistics"
```

- [ ] **Step 2: Write SC/PO/GR flow test**

Create `tests/test_sc_po_gr_flow.py`:

```python
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.gr_service import approve_gr, create_gr
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.sc_service import approve_sc, create_sc
from sc_gr_app.services.vendor_service import create_vendor


USER = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
ADMIN = {"user_id": "A1", "role": "admin", "machine_id": "M2"}


def seed_users(app_config):
    from sc_gr_app.db.connection import connect

    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            ("U1", "M1", "Requester", "requester", None, "active", "now", "now"),
        )
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            ("A1", "M2", "Admin", "admin", None, "active", "now", "now"),
        )
        conn.commit()


def test_sc_po_gr_happy_path(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(app_config, USER, {
        "sc_id": "SC1",
        "requester_id": "U1",
        "request_type": "service",
        "cost_center": 1001,
        "sc_amount": 1000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    approve_sc(app_config, ADMIN, "SC1")
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Vendor",
        "service_scope": "General Service",
    })
    create_po(app_config, USER, {
        "po_id": "PO1",
        "sc_id": "SC1",
        "vendor_id": "V1",
        "po_no": "PO001",
        "po_amount": 800,
        "status": "po_approved",
    })
    create_gr(app_config, USER, {
        "gr_id": "GR1",
        "po_id": "PO1",
        "estimated_amount": 100,
        "remark": "monthly service",
    })
    approve_gr(app_config, ADMIN, "GR1", con_value=90)

    from sc_gr_app.db.connection import connect
    with connect(app_config) as conn:
        row = conn.execute("select status, con_value from gr_requests where gr_id = 'GR1'").fetchone()

    assert row["status"] == "approved"
    assert row["con_value"] == 90
```

- [ ] **Step 3: Run failing service tests**

Run: `uv run pytest tests/test_vendor_service.py tests/test_sc_po_gr_flow.py -q`

Expected: FAIL because services do not exist.

- [ ] **Step 4: Implement services**

Implement `sc_service.py`, `vendor_service.py`, `po_service.py`, and `gr_service.py` with:

- Validation for required fields.
- Role checks using `rbac.py`.
- Lease locks for SC-affecting writes.
- `BEGIN IMMEDIATE` transactions.
- Budget checks using `budget_service.py`.
- Audit logs for every write.

Use this exact behavior:

- `create_sc`: requester or admin creates `pending` SC unless `operation_mode='backfill'` and admin provides another supported status.
- `approve_sc`: admin changes `pending` to `approved`.
- `create_vendor`: requester/admin creates visible shared vendor.
- `create_po`: requester/admin creates PO under approved SC; PO amount sum must not exceed SC amount.
- `create_gr`: requester/admin creates pending GR only if SC approved, SC No present, PO No present, PO status `po_approved`, and both SC available and OPEN PO are enough.
- `approve_gr`: admin sets GR `approved` and writes `con_value`; if `con_value > estimated_amount`, re-check derived available amounts.

- [ ] **Step 5: Run service tests**

Run: `uv run pytest tests/test_vendor_service.py tests/test_sc_po_gr_flow.py -q`

Expected: PASS.

### Task 7: Query Service

**Files:**
- Create: `sc_gr_app/services/query_service.py`
- Test: `tests/test_query_service.py`

- [ ] **Step 1: Write query tests**

Create `tests/test_query_service.py`:

```python
from tests.test_sc_po_gr_flow import ADMIN, USER, seed_users

from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.gr_service import create_gr
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.query_service import search_pos, search_scs, search_vendors
from sc_gr_app.services.sc_service import approve_sc, create_sc
from sc_gr_app.services.vendor_service import create_vendor


def seed_search_data(app_config):
    migrate(app_config)
    seed_users(app_config)
    create_sc(app_config, USER, {
        "sc_id": "SC1",
        "sc_no": "SC-ALPHA",
        "requester_id": "U1",
        "request_type": "service",
        "cost_center": 1200,
        "sc_amount": 1000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    approve_sc(app_config, ADMIN, "SC1")
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Alpha Vendor",
        "ksrm_vendor_code": "KV-1",
        "service_scope": "General Service",
    })
    create_po(app_config, USER, {
        "po_id": "PO1",
        "sc_id": "SC1",
        "vendor_id": "V1",
        "po_no": "PO-ALPHA",
        "po_amount": 600,
        "status": "po_approved",
        "contract_to": "2026-06-30",
    })
    create_gr(app_config, USER, {
        "gr_id": "GR1",
        "po_id": "PO1",
        "estimated_amount": 50,
        "remark": "alpha remark",
    })


def test_search_across_sc_vendor_po(app_config):
    seed_search_data(app_config)

    assert search_scs(app_config, text="alpha")[0]["sc_no"] == "SC-ALPHA"
    assert search_vendors(app_config, text="KV-1")[0]["vendor_name"] == "Alpha Vendor"
    assert search_pos(app_config, text="PO-ALPHA")[0]["po_no"] == "PO-ALPHA"
```

- [ ] **Step 2: Run failing query test**

Run: `uv run pytest tests/test_query_service.py -q`

Expected: FAIL because query service is missing.

- [ ] **Step 3: Implement query service**

Create query functions:

- `search_scs(config, text=None, filters=None, sort="created_at", direction="desc", limit=100, offset=0)`
- `search_vendors(config, text=None, filters=None, sort="vendor_name", direction="asc", limit=100, offset=0)`
- `search_pos(config, text=None, filters=None, sort="created_at", direction="desc", limit=100, offset=0)`
- `search_grs(config, text=None, filters=None, sort="created_at", direction="desc", limit=100, offset=0)`
- `search_audit_logs(config, filters=None, sort="created_at", direction="desc", limit=100, offset=0)`

Use explicit allowlists for sortable fields. Do not string-concatenate unvalidated sort fields.

- [ ] **Step 4: Run query tests**

Run: `uv run pytest tests/test_query_service.py -q`

Expected: PASS.

### Task 8: pywebview API Bridge

**Files:**
- Create: `sc_gr_app/api/__init__.py`
- Create: `sc_gr_app/api/schemas.py`
- Create: `sc_gr_app/api/bridge.py`
- Create: `sc_gr_app/app_shell.py`

- [ ] **Step 1: Implement response wrapper**

Create `sc_gr_app/api/schemas.py`:

```python
from sc_gr_app.errors import AppError


def ok(data=None) -> dict:
    return {"ok": True, "data": data}


def fail(exc: Exception) -> dict:
    if isinstance(exc, AppError):
        return {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    return {"ok": False, "error": {"code": "UNEXPECTED_ERROR", "message": str(exc)}}
```

- [ ] **Step 2: Implement bridge**

Create `sc_gr_app/api/__init__.py` empty.

Create `sc_gr_app/api/bridge.py`:

```python
from sc_gr_app.api.schemas import fail, ok
from sc_gr_app.config import AppConfig
from sc_gr_app.identity import get_7_digit_id
from sc_gr_app.services import query_service
from sc_gr_app.services.user_service import get_user_by_machine_id


class ApiBridge:
    def __init__(self, config: AppConfig):
        self.config = config

    def current_user(self):
        try:
            machine_id = get_7_digit_id()
            return ok(get_user_by_machine_id(self.config, machine_id))
        except Exception as exc:
            return fail(exc)

    def search_scs(self, payload=None):
        try:
            payload = payload or {}
            return ok(query_service.search_scs(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_vendors(self, payload=None):
        try:
            payload = payload or {}
            return ok(query_service.search_vendors(self.config, **payload))
        except Exception as exc:
            return fail(exc)

    def search_pos(self, payload=None):
        try:
            payload = payload or {}
            return ok(query_service.search_pos(self.config, **payload))
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 3: Implement app shell**

Create `sc_gr_app/app_shell.py`:

```python
from pathlib import Path

import webview

from sc_gr_app.api.bridge import ApiBridge
from sc_gr_app.config import default_config
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.user_service import seed_default_admin


def run_app() -> None:
    config = default_config()
    migrate(config)
    seed_default_admin(config)
    html_path = Path(__file__).parent / "web" / "index.html"
    bridge = ApiBridge(config)
    webview.create_window(
        "SC GR Management",
        url=str(html_path),
        js_api=bridge,
        width=1280,
        height=820,
        min_size=(1100, 700),
    )
    webview.start(debug=True)
```

- [ ] **Step 4: Run import check**

Run: `uv run python -c "from sc_gr_app.app_shell import run_app; print('ok')"`

Expected: prints `ok`.

### Task 9: Frontend Design And UI Implementation

**Files:**
- Create: `sc_gr_app/web/index.html`
- Create: `sc_gr_app/web/styles.css`
- Create: `sc_gr_app/web/app.js`
- Create: `sc_gr_app/web/components/api.js`
- Create: `sc_gr_app/web/components/format.js`
- Create: `sc_gr_app/web/components/state.js`
- Create: `sc_gr_app/web/components/tables.js`
- Create: `sc_gr_app/web/components/views.js`

**Required skill:** Before writing UI code, use `frontend-design`.

Design direction:

- Bright professional operations dashboard.
- No dark mode.
- Main palette: warm white background, clear blue primary, green status accents, amber warning accents, neutral table lines.
- Avoid marketing hero sections.
- Dense but readable layout for repeated daily use.
- Use a left navigation rail and a top toolbar with search.
- Tables must support visible filters, sorting, empty states, loading states, and error states.
- Cards are allowed only for repeated summary metrics or compact panels; do not nest cards.

- [ ] **Step 1: Write frontend structure**

Create `index.html` with:

- App shell.
- Left navigation: Home, SC, Vendor, PO, GR, Logs, System.
- Main content region.
- Template containers for toolbar, filters, tables, and detail drawer.

- [ ] **Step 2: Write bright CSS**

Create CSS variables:

```css
:root {
  --bg: #f7f9fc;
  --surface: #ffffff;
  --surface-muted: #eef3f8;
  --text: #1d2733;
  --muted: #667789;
  --line: #d8e1ea;
  --primary: #1f73d1;
  --primary-soft: #dcecff;
  --success: #16875d;
  --warning: #b7791f;
  --danger: #c2413b;
}
```

Implement:

- Fixed sidebar.
- Content header.
- Filter bar.
- Sortable data table.
- Status badges for SC, PO, GR.
- Buttons with clear hover and focus states.
- Responsive minimum layout for 1100px width.

- [ ] **Step 3: Implement frontend API wrapper**

`components/api.js`:

```javascript
export async function callApi(name, payload = {}) {
  const api = window.pywebview?.api;
  if (!api || !api[name]) {
    throw new Error(`API not available: ${name}`);
  }
  const result = await api[name](payload);
  if (!result.ok) {
    throw new Error(result.error?.message || "Unknown API error");
  }
  return result.data;
}
```

- [ ] **Step 4: Implement table rendering**

`components/tables.js` must support:

- columns.
- rows.
- sort key.
- sort direction.
- click header to sort.
- empty state.
- loading state.

- [ ] **Step 5: Implement views**

`components/views.js` must include:

- SC list view with text search and field filters.
- vendor list view with service scope filter.
- PO list view with PO status, contract_to, OPEN PO filters.
- GR list view with status and amount filters.
- Logs view with date and action type filters.

- [ ] **Step 6: Implement app boot**

`app.js`:

- load current user.
- render navigation.
- default to SC list.
- route clicks without page reload.
- show user role and machine authorization state.

- [ ] **Step 7: Manual frontend verification**

Run: `uv run python -m sc_gr_app.main`

Expected:

- Window opens.
- Bright UI loads.
- No dark mode.
- Navigation works.
- Tables show loading and empty states without layout shifting.
- Text does not overflow buttons or table headers.

### Task 10: Packaging And Operations Tools

**Files:**
- Create: `packaging/build.ps1`
- Create: `packaging/app.spec`
- Modify: `README.md`

- [ ] **Step 1: Add build script**

Create `packaging/build.ps1`:

```powershell
uv sync --all-groups
uv run pytest -q
uv run pyinstaller packaging/app.spec
```

- [ ] **Step 2: Add PyInstaller spec**

Create `packaging/app.spec` configured to include `sc_gr_app/web` and `sc_gr_app/db/schema.sql`.

- [ ] **Step 3: Add README**

Document:

- How to install dependencies with `uv sync --all-groups`.
- How to run tests with `uv run pytest -q`.
- How to start the app with `uv run python -m sc_gr_app.main`.
- How to set shared DB path later.
- How to build Windows executable.
- How to recover from stale locks.

- [ ] **Step 4: Verify packaging command**

Run: `powershell -ExecutionPolicy Bypass -File packaging/build.ps1`

Expected:

- pytest passes.
- PyInstaller produces a Windows executable under `dist/`.

## Test Strategy

Run these before considering implementation complete:

```powershell
uv run pytest -q
uv run python -c "from sc_gr_app.db.migrations import migrate; from sc_gr_app.config import default_config; migrate(default_config()); print('migration ok')"
uv run python -c "from sc_gr_app.app_shell import run_app; print('app import ok')"
```

Manual checks:

- Create requester and admin users.
- Create SC as requester.
- Approve SC as admin.
- Create vendor.
- Create PO with `po_approved`.
- Create pending GR.
- Approve GR with Con Value.
- Confirm SC available and OPEN PO changed.
- Search SC by vendor name.
- Search vendor by KSRM vendor code.
- Search PO by contract no and sort by contract_to.
- Search GR by remark and filter by status.
- View logs as requester and admin.
- Simulate stale lock and verify admin cleanup path.

## Self-Review Checklist

- SC has no `expired` status.
- SC service period does not block GR.
- PO `contract_to` is the only date identified for later email reminder.
- `gr_requests` has no `sc_id`, `reason`, `finance_reference_no`, or `actual_amount`.
- `con_value` is used everywhere for approved GR amount.
- `open_po_amount` is derived, not stored.
- vendor is independent and reusable.
- SC/vendor/PO/GR/log search, filters, sorting, and pagination are planned.
- Frontend plan requires `frontend-design`, bright theme, no dark mode.
- Reads are lock-free; writes are locked.


