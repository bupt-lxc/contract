# PO Manual Annual Amounts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add PO-level manual annual amount records for provision and to-be-GR, show them on PO detail, and include them in the PO annual report export without changing budget, GR, workflow, email, notification, or operation-record behavior.

**Architecture:** Store records in a new `po_manual_amounts` table keyed by `manual_amount_id` with a uniqueness rule on `(po_id, year, type)`. The PO service owns validation, visibility, mutation permission, detail loading, deletion cleanup, and annual-report joins; the API bridge exposes thin methods and timestamp formatting; `PoDetailView` renders and mutates the records through dedicated bridge calls.

**Tech Stack:** Python, SQLite migrations, pytest, Vue 3 Composition API, Element Plus, existing pywebview bridge.

---

## File Map

- `sc_gr_app/db/migrations.py`: bump schema to v40 and create `po_manual_amounts`.
- `sc_gr_app/db/schema.sql`: add `po_manual_amounts` to fresh schema creation.
- `sc_gr_app/services/po_service.py`: add manual amount CRUD helpers, permission flag, PO detail data, PO deletion cleanup, and annual report values.
- `sc_gr_app/services/sc_service.py`: attach manual amounts to nested PO rows and clean them when deleting an SC directly.
- `sc_gr_app/api/bridge.py`: expose list/create/delete bridge methods and format top-level and nested manual amount timestamps.
- `frontend/src/composables/usePo.js`: add bridge helpers for list/create/delete manual amount records.
- `frontend/src/views/PoDetailView.vue`: add the detail-only section, create dialog, delete action, and refresh logic.
- `frontend/src/i18n/locales/en-US.js`: add English labels.
- `frontend/src/i18n/locales/zh-CN.js`: add Chinese labels.
- `tests/test_migrations.py`: assert v40 schema, constraints, and index.
- `tests/test_po_manual_amounts.py`: cover service create/list/delete, permission, detail, deletion cleanup, and calculation non-interference.
- `tests/test_po_annual_report.py`: cover manual columns in PO annual report and blank SC-only rows.
- `tests/test_gr_annual_report.py`: verify manual amounts do not affect GR annual report.
- `tests/test_api_bridge.py`: cover bridge forwarding and timestamp formatting for manual amounts.

## Invariants

- Manual amounts do not call `write_operation_record`, `notification_service`, or email/outlook helpers.
- Manual amounts do not change `compute_po_budget`, `compute_sc_budget`, GR status behavior, PO open amount, SC amount, PO amount, or validation comparing PO/SC/GR amounts.
- Manual amounts do not affect GR annual report, PO search/filter/list columns, regular PO export, PO import, PO template download, dashboards, or batch import/export.
- Add/delete permission is exposed as `can_manage_po_manual_amounts`; do not reuse `can_manage_po` because finished POs must remain editable for this feature. For SC-linked POs, visibility and mutation are based on the current owning SC requester, not the historical `pos.requester_id`; for independent POs with no SC, visibility and mutation use the PO requester. SC assignees retain read-only visibility only.
- `year` is a four-digit string. `amount` accepts positive, zero, and negative numeric values.
- Duplicate `(po_id, year, type)` raises `ConflictError`.
- Annual report missing manual records render as `""`, not `0`.
- SC-only annual report rows keep manual columns blank.

---

### Task 1: Migration V40

**Files:**
- Modify: `sc_gr_app/db/migrations.py`
- Modify: `sc_gr_app/db/schema.sql`
- Modify: `tests/test_migrations.py`

- [ ] **Step 1: Write the failing migration tests**

Add `Path` to the imports in `tests/test_migrations.py`:

```python
from pathlib import Path
```

Add these tests near the other schema tests in `tests/test_migrations.py`:

```python
def test_migration_creates_po_manual_amounts_table(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        columns = {
            row[1]: row[2]
            for row in conn.execute("PRAGMA table_info(po_manual_amounts)")
        }
        indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(po_manual_amounts)")
        }

    assert columns.items() >= {
        "manual_amount_id": "TEXT",
        "po_id": "TEXT",
        "year": "TEXT",
        "type": "TEXT",
        "amount": "REAL",
        "created_by": "TEXT",
        "created_at": "TEXT",
    }.items()
    assert "idx_po_manual_amounts_po_id" in indexes


def test_schema_sql_includes_po_manual_amounts():
    schema_sql = Path("sc_gr_app/db/schema.sql").read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS po_manual_amounts" in schema_sql
    assert "UNIQUE(po_id, year, type)" in schema_sql
    assert "idx_po_manual_amounts_po_id" in schema_sql


def test_po_manual_amounts_constraints(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        conn.executescript(
            """
            INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
            VALUES ('U1', 'M1', 'Requester', 'requester', 'u1@test.local', 'active', '2026-01-01', '2026-01-01');

            INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
            VALUES ('V1', 'Vendor', 'General', 'U1', '2026-01-01', '2026-01-01');

            INSERT INTO pos (po_id, vendor_id, requester_id, po_amount, status, created_at, updated_at)
            VALUES ('PO1', 'V1', 'U1', 100, 'active', '2026-01-01', '2026-01-01');
            """
        )
        conn.execute(
            """
            INSERT INTO po_manual_amounts (
              manual_amount_id, po_id, year, type, amount, created_by, created_at
            ) VALUES ('PMA-1', 'PO1', '2025', 'provision', -10, 'U1', '2026-01-01')
            """
        )
        try:
            conn.execute(
                """
                INSERT INTO po_manual_amounts (
                  manual_amount_id, po_id, year, type, amount, created_by, created_at
                ) VALUES ('PMA-2', 'PO1', '2025', 'provision', 20, 'U1', '2026-01-01')
                """
            )
        except sqlite3.IntegrityError as exc:
            assert "UNIQUE" in str(exc)
        else:
            raise AssertionError("duplicate manual amount was accepted")
        try:
            conn.execute(
                """
                INSERT INTO po_manual_amounts (
                  manual_amount_id, po_id, year, type, amount, created_by, created_at
                ) VALUES ('PMA-3', 'PO1', '25', 'provision', 20, 'U1', '2026-01-01')
                """
            )
        except sqlite3.IntegrityError as exc:
            assert "CHECK" in str(exc)
        else:
            raise AssertionError("invalid year was accepted")
```

- [ ] **Step 2: Run migration tests and verify failure**

Run:

```powershell
pytest tests/test_migrations.py::test_migration_creates_po_manual_amounts_table tests/test_migrations.py::test_po_manual_amounts_constraints -q
```

Expected: both tests fail because `po_manual_amounts` does not exist.

- [ ] **Step 3: Add migration v40**

In `sc_gr_app/db/migrations.py`, change:

```python
SCHEMA_VERSION = 39
```

to:

```python
SCHEMA_VERSION = 40
```

Add this function after `_migrate_v39`:

```python
def _migrate_v40(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS po_manual_amounts (
            manual_amount_id TEXT PRIMARY KEY,
            po_id TEXT NOT NULL REFERENCES pos(po_id),
            year TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]'),
            type TEXT NOT NULL CHECK (type IN ('provision', 'to_be_gr')),
            amount REAL NOT NULL,
            created_by TEXT NOT NULL REFERENCES users(user_id),
            created_at TEXT NOT NULL,
            UNIQUE(po_id, year, type)
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_po_manual_amounts_po_id "
        "ON po_manual_amounts(po_id)"
    )
    _record(conn, 40)
```

In `migrate()`, immediately after the v39 block, follow the existing `_applied_versions` style and add:

```python
            if 40 not in _applied_versions(conn):
                conn.execute("BEGIN")
                _migrate_v40(conn)
                conn.commit()
```

Do not introduce a `record_migration` function. This codebase records migration versions with `_record(conn, version)` inside each `_migrate_vN` function.

Update `sc_gr_app/db/schema.sql` after the `pos` table and before dependent PO child tables:

```sql
CREATE TABLE IF NOT EXISTS po_manual_amounts (
  manual_amount_id TEXT PRIMARY KEY,
  po_id TEXT NOT NULL REFERENCES pos(po_id),
  year TEXT NOT NULL CHECK (year GLOB '[0-9][0-9][0-9][0-9]'),
  type TEXT NOT NULL CHECK (type IN ('provision', 'to_be_gr')),
  amount REAL NOT NULL,
  created_by TEXT NOT NULL REFERENCES users(user_id),
  created_at TEXT NOT NULL,
  UNIQUE(po_id, year, type)
);

CREATE INDEX IF NOT EXISTS idx_po_manual_amounts_po_id ON po_manual_amounts(po_id);
```

- [ ] **Step 4: Run migration tests and verify pass**

Run:

```powershell
pytest tests/test_migrations.py tests/test_initial_db.py -q
```

Expected: all selected tests pass and recorded migration versions include 40.

- [ ] **Step 5: Commit**

Run:

```powershell
git add sc_gr_app/db/migrations.py sc_gr_app/db/schema.sql tests/test_migrations.py
git commit -m "feat: add PO manual amounts migration"
```

---

### Task 2: PO Service Manual Amount CRUD

**Files:**
- Create: `tests/test_po_manual_amounts.py`
- Modify: `sc_gr_app/services/po_service.py`

- [ ] **Step 1: Write service CRUD and permission tests**

Create `tests/test_po_manual_amounts.py` with this starting content:

```python
import sqlite3

import pytest

from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.services import po_service


ADMIN = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "M_ADMIN"}
PO_REQUESTER = {"user_id": "U_PO", "role": "requester", "machine_id": "M_PO"}
SC_REQUESTER = {"user_id": "U_SC", "role": "requester", "machine_id": "M_SC"}
SC_ASSIGNEE = {"user_id": "U_ASSIGNEE", "role": "requester", "machine_id": "M_ASSIGNEE"}
OTHER = {"user_id": "U_OTHER", "role": "requester", "machine_id": "M_OTHER"}


def _seed(config, po_status="active"):
    migrate(config)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(
        f"""
        INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
        VALUES
          ('U_ADMIN', 'M_ADMIN', 'Admin User', 'admin', 'admin@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_PO', 'M_PO', 'PO Requester', 'requester', 'po@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_SC', 'M_SC', 'SC Requester', 'requester', 'sc@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_ASSIGNEE', 'M_ASSIGNEE', 'SC Assignee', 'requester', 'assignee@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_OTHER', 'M_OTHER', 'Other User', 'requester', 'other@test.local', 'active', '2026-01-01', '2026-01-01');

        INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('V1', 'Vendor One', 'General', 'U_ADMIN', '2026-01-01', '2026-01-01');

        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at
        )
        VALUES ('SC1', 'SC-001', 'U_SC', 'new', 1000, 10000, '2026-01-01', '2026-12-31', 'approved', 'Approved SC', 'U_ADMIN', '2026-01-01', '2026-01-01');

        INSERT INTO sc_assignees (sc_id, user_id)
        VALUES ('SC1', 'U_ASSIGNEE');

        INSERT INTO pos (
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
          created_at, updated_at, finished_at
        )
        VALUES
          ('PO1', 'SC1', 'V1', 'PO-001', 'U_PO', 5000, '{po_status}', '2026-01-01', '2026-01-01', '2026-06-01'),
          ('PO_INDEPENDENT', NULL, 'V1', 'PO-INDEP', 'U_PO', 3000, '{po_status}', '2026-01-01', '2026-01-01', '2026-06-01');
        """
    )
    conn.commit()
    conn.close()


def test_create_list_and_delete_manual_amounts(app_config):
    _seed(app_config)

    provision = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": -10}
    )
    to_be_gr = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2026", "type": "to_be_gr", "amount": 0}
    )

    assert provision["manual_amount_id"].startswith("PMA-")
    assert provision["po_id"] == "PO1"
    assert provision["year"] == "2025"
    assert provision["type"] == "provision"
    assert provision["amount"] == -10
    assert provision["created_by"] == "U_ADMIN"
    assert provision["created_by_name"] == "Admin User"
    assert provision["created_at"]

    rows = po_service.list_po_manual_amounts(app_config, ADMIN, "PO1")
    assert [row["manual_amount_id"] for row in rows] == [
        to_be_gr["manual_amount_id"],
        provision["manual_amount_id"],
    ]

    result = po_service.delete_po_manual_amount(
        app_config, ADMIN, provision["manual_amount_id"]
    )
    assert result == {"deleted": True, "manual_amount_id": provision["manual_amount_id"]}
    remaining = po_service.list_po_manual_amounts(app_config, ADMIN, "PO1")
    assert [row["manual_amount_id"] for row in remaining] == [to_be_gr["manual_amount_id"]]


def test_manual_amount_validation_and_duplicate(app_config):
    _seed(app_config)

    with pytest.raises(ValidationError, match="year must be a 4-digit string"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "26", "type": "provision", "amount": 1}
        )
    with pytest.raises(ValidationError, match="type must be"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "other", "amount": 1}
        )
    with pytest.raises(ValidationError, match="amount must be a number"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": "abc"}
        )
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": 1}
    )
    with pytest.raises(ConflictError, match="already exists"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": 2}
        )
    with pytest.raises(NotFound):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO_MISSING", {"year": "2026", "type": "provision", "amount": 1}
        )


def test_manual_amount_mutation_permissions_for_linked_and_independent_pos(app_config):
    _seed(app_config)

    for index, user in enumerate((ADMIN, SC_REQUESTER), start=1):
        created = po_service.create_po_manual_amount(
            app_config,
            user,
            "PO1",
            {"year": str(2020 + index), "type": "provision", "amount": index},
        )
        assert created["created_by"] == user["user_id"]
        assert po_service.delete_po_manual_amount(
            app_config, user, created["manual_amount_id"]
        )["deleted"] is True

    independent = po_service.create_po_manual_amount(
        app_config,
        PO_REQUESTER,
        "PO_INDEPENDENT",
        {"year": "2025", "type": "provision", "amount": 10},
    )
    assert po_service.delete_po_manual_amount(
        app_config, PO_REQUESTER, independent["manual_amount_id"]
    )["deleted"] is True

    for user in (PO_REQUESTER, SC_ASSIGNEE, OTHER):
        with pytest.raises(PermissionDenied):
            po_service.create_po_manual_amount(
                app_config, user, "PO1", {"year": "2026", "type": "provision", "amount": 1}
            )

    with pytest.raises(PermissionDenied):
        po_service.create_po_manual_amount(
            app_config, OTHER, "PO_INDEPENDENT", {"year": "2026", "type": "provision", "amount": 1}
        )


def test_manual_amounts_allowed_on_finished_po(app_config):
    _seed(app_config, po_status="finished")

    created = po_service.create_po_manual_amount(
        app_config, SC_REQUESTER, "PO1", {"year": "2026", "type": "to_be_gr", "amount": 12}
    )

    assert created["amount"] == 12
    assert po_service.delete_po_manual_amount(
        app_config, SC_REQUESTER, created["manual_amount_id"]
    )["deleted"] is True
```

- [ ] **Step 2: Run service tests and verify failure**

Run:

```powershell
pytest tests/test_po_manual_amounts.py -q
```

Expected: tests fail because service functions do not exist.

- [ ] **Step 3: Add service helpers**

In `sc_gr_app/services/po_service.py`, add imports:

```python
import re
import uuid
```

Add these constants and helpers near `_po_permissions`:

```python
MANUAL_AMOUNT_TYPES = {"provision", "to_be_gr"}


def _manual_amount_row_to_dict(row) -> dict:
    item = _row_to_dict(row)
    if item.get("amount") is not None:
        item["amount"] = float(item["amount"])
    return item


def _manual_amount_rows(conn, po_id: str) -> list[dict]:
    return [
        _manual_amount_row_to_dict(row)
        for row in conn.execute(
            """
            select pma.*, u.user_name as created_by_name
            from po_manual_amounts pma
            left join users u on u.user_id = pma.created_by
            where pma.po_id = ?
            order by pma.year desc, pma.type asc, pma.created_at desc
            """,
            (po_id,),
        )
    ]


def _get_manual_amount_or_raise(conn, manual_amount_id: str) -> dict:
    row = conn.execute(
        """
        select pma.*, u.user_name as created_by_name
        from po_manual_amounts pma
        left join users u on u.user_id = pma.created_by
        where pma.manual_amount_id = ?
        """,
        (manual_amount_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"Manual PO amount not found: {manual_amount_id}")
    return _manual_amount_row_to_dict(row)


def _is_parent_sc_requester(current_user: dict, po: dict, conn) -> bool:
    if not po.get("sc_id"):
        return False
    row = conn.execute(
        "select requester_id from sc_records where sc_id = ?",
        (po["sc_id"],),
    ).fetchone()
    return row is not None and row["requester_id"] == current_user.get("user_id")


def _can_manage_po_manual_amounts(current_user: dict, po: dict, conn) -> bool:
    if current_user.get("role") == "admin":
        return True
    if po.get("sc_id"):
        return _is_parent_sc_requester(current_user, po, conn)
    return current_user.get("user_id") == po.get("requester_id")


def _assert_can_manage_po_manual_amounts(current_user: dict, po: dict, conn) -> None:
    if not _can_manage_po_manual_amounts(current_user, po, conn):
        raise PermissionDenied("Only admin, owning SC requester, or independent PO requester can manage manual PO amounts")


def _validate_manual_amount_data(data: dict) -> tuple[str, str, float]:
    year = data.get("year")
    if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
        raise ValidationError("year must be a 4-digit string")

    record_type = data.get("type")
    if record_type not in MANUAL_AMOUNT_TYPES:
        raise ValidationError("type must be 'provision' or 'to_be_gr'")

    try:
        amount = Decimal(str(data.get("amount")))
    except Exception:
        raise ValidationError("amount must be a number") from None
    if not amount.is_finite():
        raise ValidationError("amount must be a number")

    return year, record_type, float(amount)
```

Update `_assert_can_view_po` so SC-linked PO visibility follows the owning SC requester and SC assignee rules, while independent PO visibility still follows the PO requester:

```python
def _assert_can_view_po(current_user: dict, po: dict, conn) -> None:
    if current_user.get("role") == "admin":
        return
    if po.get("sc_id"):
        if _is_parent_sc_requester(current_user, po, conn):
            return
        assignee_row = conn.execute(
            "SELECT 1 FROM sc_assignees WHERE sc_id = ? AND user_id = ?",
            (po["sc_id"], current_user.get("user_id")),
        ).fetchone()
        if assignee_row is not None:
            return
        raise PermissionDenied("PO is not visible")
    if (
        current_user.get("role") == "requester"
        and current_user.get("user_id") == po["requester_id"]
    ):
        return
    raise PermissionDenied("PO is not visible")
```

Change `_po_permissions` to require a connection and include the new flag. Keep existing PO manage/delete semantics intact; the new finished-PO edit behavior must live only in `can_manage_po_manual_amounts`:

```python
def _po_permissions(current_user: dict, po: dict, conn) -> dict:
    is_admin = current_user.get("role") == "admin"
    is_owner = current_user.get("user_id") == po["requester_id"]
    can_manage = (is_admin or is_owner) and po["status"] in ("draft", "active")
    return {
        "is_admin": is_admin,
        "can_delete_po": is_admin or is_owner,
        "can_manage_po": can_manage,
        "can_manage_gr": can_manage,
        "can_manage_po_manual_amounts": _can_manage_po_manual_amounts(current_user, po, conn),
    }
```

Add the public service methods before `create_po`:

```python
def list_po_manual_amounts(config: AppConfig, current_user: dict, po_id: str) -> list[dict]:
    with connect(config) as conn:
        po = _get_po_or_raise(conn, po_id)
        _assert_can_view_po(current_user, po, conn)
        return _manual_amount_rows(conn, po_id)


def create_po_manual_amount(config: AppConfig, current_user: dict, po_id: str, data: dict) -> dict:
    with connect(config) as conn:
        po = _get_po_or_raise(conn, po_id)
        _assert_can_view_po(current_user, po, conn)
        _assert_can_manage_po_manual_amounts(current_user, po, conn)
        year, record_type, amount = _validate_manual_amount_data(data)
        manual_amount_id = f"PMA-{uuid.uuid4().hex}"
        timestamp = utc_now()
        try:
            conn.execute(
                """
                insert into po_manual_amounts (
                  manual_amount_id, po_id, year, type, amount, created_by, created_at
                ) values (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    manual_amount_id,
                    po_id,
                    year,
                    record_type,
                    amount,
                    current_user["user_id"],
                    timestamp,
                ),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            if "UNIQUE" in str(exc):
                raise ConflictError("Manual amount already exists for this PO, year, and type") from None
            raise
        return _get_manual_amount_or_raise(conn, manual_amount_id)


def delete_po_manual_amount(config: AppConfig, current_user: dict, manual_amount_id: str) -> dict:
    with connect(config) as conn:
        row = conn.execute(
            """
            select pma.*, po.requester_id, po.sc_id, po.status
            from po_manual_amounts pma
            join pos po on po.po_id = pma.po_id
            where pma.manual_amount_id = ?
            """,
            (manual_amount_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"Manual PO amount not found: {manual_amount_id}")
        po = {
            "po_id": row["po_id"],
            "requester_id": row["requester_id"],
            "sc_id": row["sc_id"],
            "status": row["status"],
        }
        _assert_can_view_po(current_user, po, conn)
        _assert_can_manage_po_manual_amounts(current_user, po, conn)
        conn.execute(
            "delete from po_manual_amounts where manual_amount_id = ?",
            (manual_amount_id,),
        )
        conn.commit()
    return {"deleted": True, "manual_amount_id": manual_amount_id}
```

- [ ] **Step 4: Run service CRUD tests and verify pass**

Run:

```powershell
pytest tests/test_po_manual_amounts.py -q
```

Expected: the four tests in this task pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add sc_gr_app/services/po_service.py tests/test_po_manual_amounts.py
git commit -m "feat: add PO manual amount service"
```

---

### Task 3: Detail Data and Delete Cleanup

**Files:**
- Modify: `tests/test_po_manual_amounts.py`
- Modify: `sc_gr_app/services/po_service.py`
- Modify: `sc_gr_app/services/sc_service.py`

- [ ] **Step 1: Add failing detail and cleanup tests**

Append these tests to `tests/test_po_manual_amounts.py`:

```python
def test_po_and_sc_detail_include_manual_amounts_and_permission(app_config):
    _seed(app_config)
    created = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 11}
    )

    po_detail = po_service.get_po_detail(app_config, SC_REQUESTER, "PO1")
    assert po_detail["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert po_detail["manual_amounts"][0]["created_by_name"] == "Admin User"
    assert po_detail["permissions"]["can_manage_po_manual_amounts"] is True

    assignee_detail = po_service.get_po_detail(app_config, SC_ASSIGNEE, "PO1")
    assert assignee_detail["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert assignee_detail["permissions"]["can_manage_po_manual_amounts"] is False

    with pytest.raises(PermissionDenied):
        po_service.get_po_detail(app_config, PO_REQUESTER, "PO1")

    from sc_gr_app.services import sc_service

    sc_detail = sc_service.get_sc_detail(app_config, SC_REQUESTER, "SC1")
    po_row = next(row for row in sc_detail["pos"] if row["po_id"] == "PO1")
    assert po_row["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert po_row["can_manage_po_manual_amounts"] is True
    assert sc_detail["permissions"]["can_manage_po_manual_amounts"] is True


def test_manual_amounts_do_not_change_po_budget(app_config):
    _seed(app_config)
    before = po_service.get_po_detail(app_config, ADMIN, "PO1")["po"]["open_po_amount"]

    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 999999}
    )

    after = po_service.get_po_detail(app_config, ADMIN, "PO1")["po"]["open_po_amount"]
    assert after == before


def test_delete_po_removes_manual_amounts(app_config):
    _seed(app_config, po_status="draft")
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 11}
    )

    po_service.delete_po(app_config, SC_REQUESTER, "PO1")

    with sqlite3.connect(app_config.db_path) as conn:
        count = conn.execute("select count(*) from po_manual_amounts").fetchone()[0]
    assert count == 0
```

Add this SC-delete-specific test to avoid relying only on `delete_po`:

```python
def test_delete_sc_removes_child_po_manual_amounts(app_config):
    _seed(app_config, po_status="draft")
    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute("update sc_records set status = 'draft' where sc_id = 'SC1'")
        conn.commit()
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "to_be_gr", "amount": 22}
    )

    from sc_gr_app.services import sc_service

    sc_service.delete_sc(app_config, SC_REQUESTER, "SC1")

    with sqlite3.connect(app_config.db_path) as conn:
        count = conn.execute("select count(*) from po_manual_amounts").fetchone()[0]
    assert count == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
pytest tests/test_po_manual_amounts.py -q
```

Expected: detail and cleanup tests fail because data is not attached and cleanup is not wired.

- [ ] **Step 3: Attach manual amounts to PO detail**

In `get_po_detail`, fetch manual amounts and permissions before leaving the database context:

```python
        manual_amounts = _manual_amount_rows(conn, po_id)
        permissions = _po_permissions(current_user, po, conn)
```

Change the returned dict to:

```python
    return {
        "po": po,
        "manual_amounts": manual_amounts,
        "calloff_scs": calloff_scs if is_fc_po else [],
        "operation_records": records,
        "permissions": permissions,
    }
```

Keep all budget computation logic unchanged.

- [ ] **Step 4: Attach manual amounts to SC detail**

Inside `get_sc_detail`, after `pos` is loaded and before the connection closes, fetch manual records for all child POs:

```python
        manual_amounts_by_po: dict[str, list[dict]] = {}
        if pos:
            placeholders = ",".join("?" for _ in pos)
            manual_rows = conn.execute(
                f"""
                select pma.*, u.user_name as created_by_name
                from po_manual_amounts pma
                left join users u on u.user_id = pma.created_by
                where pma.po_id in ({placeholders})
                order by pma.year desc, pma.type asc, pma.created_at desc
                """,
                [po["po_id"] for po in pos],
            ).fetchall()
            for row in manual_rows:
                item = dict(row)
                if item.get("amount") is not None:
                    item["amount"] = float(item["amount"])
                manual_amounts_by_po.setdefault(item["po_id"], []).append(item)
```

After the connection closes, add the records to each PO row:

```python
    for po in pos:
        po["manual_amounts"] = manual_amounts_by_po.get(po["po_id"], [])
        po["can_manage_po_manual_amounts"] = (
            current_user.get("role") == "admin"
            or current_user.get("user_id") == sc.get("requester_id")
        )
```

Update `_sc_permissions` in the same file to include a detail-level flag for the current SC:

```python
        "can_manage_po_manual_amounts": is_admin or is_owner,
```

Use the existing `is_admin` and `is_owner` variables in `_sc_permissions`.

- [ ] **Step 5: Clean manual records during PO and SC delete**

In `delete_po`, before deleting the PO row, add:

```python
                conn.execute("DELETE FROM po_manual_amounts WHERE po_id = ?", (po_id,))
```

Place it before:

```python
                conn.execute("DELETE FROM pos WHERE po_id = ?", (po_id,))
```

In `delete_sc`, inside the loop that deletes GRs and child POs, add:

```python
                    conn.execute("DELETE FROM po_manual_amounts WHERE po_id = ?", (po_id,))
```

Place it before:

```python
                    conn.execute("DELETE FROM pos WHERE po_id = ?", (po_id,))
```

- [ ] **Step 6: Run tests and verify pass**

Run:

```powershell
pytest tests/test_po_manual_amounts.py tests/test_po_service.py tests/test_sc_service.py -q
```

Expected: selected tests pass.

- [ ] **Step 7: Commit**

Run:

```powershell
git add sc_gr_app/services/po_service.py sc_gr_app/services/sc_service.py tests/test_po_manual_amounts.py
git commit -m "feat: include PO manual amounts in detail data"
```

---

### Task 4: API Bridge Methods and Timestamp Formatting

**Files:**
- Modify: `sc_gr_app/api/bridge.py`
- Modify: `tests/test_api_bridge.py`

- [ ] **Step 1: Add bridge tests**

Append these tests to `tests/test_api_bridge.py`:

```python
def test_bridge_manual_amount_methods_forward_payload(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    current_user = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "1234567"}
    calls = []

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )
    monkeypatch.setattr(
        bridge.po_service,
        "list_po_manual_amounts",
        lambda config, user, po_id: calls.append(("list", config, user, po_id)) or [
            {"manual_amount_id": "PMA-1", "created_at": "2026-07-09T00:00:00+00:00"}
        ],
    )
    monkeypatch.setattr(
        bridge.po_service,
        "create_po_manual_amount",
        lambda config, user, po_id, data: calls.append(("create", config, user, po_id, data)) or {
            "manual_amount_id": "PMA-2",
            "created_at": "2026-07-09T01:00:00+00:00",
        },
    )
    monkeypatch.setattr(
        bridge.po_service,
        "delete_po_manual_amount",
        lambda config, user, manual_amount_id: calls.append(("delete", config, user, manual_amount_id)) or {
            "deleted": True,
            "manual_amount_id": manual_amount_id,
        },
    )

    api = bridge.ApiBridge(app_config)

    assert api.list_po_manual_amounts({"po_id": "PO1"})["ok"] is True
    assert api.create_po_manual_amount(
        {"po_id": "PO1", "data": {"year": "2026", "type": "to_be_gr", "amount": 1}}
    )["ok"] is True
    assert api.delete_po_manual_amount({"manual_amount_id": "PMA-2"}) == {
        "ok": True,
        "data": {"deleted": True, "manual_amount_id": "PMA-2"},
    }
    assert calls[0] == ("list", app_config, current_user, "PO1")
    assert calls[1] == (
        "create",
        app_config,
        current_user,
        "PO1",
        {"year": "2026", "type": "to_be_gr", "amount": 1},
    )
    assert calls[2] == ("delete", app_config, current_user, "PMA-2")


def test_bridge_formats_manual_amount_timestamps_in_details(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    current_user = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "1234567"}
    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: current_user,
    )
    monkeypatch.setattr(
        bridge.po_service,
        "get_po_detail",
        lambda config, user, po_id: {
            "po": {"po_id": po_id},
            "manual_amounts": [
                {"manual_amount_id": "PMA-1", "created_at": "2026-07-09T00:00:00+00:00"}
            ],
        },
    )
    monkeypatch.setattr(
        bridge.sc_service,
        "get_sc_detail",
        lambda config, user, sc_id: {
            "sc": {"sc_id": sc_id},
            "pos": [
                {
                    "po_id": "PO1",
                    "manual_amounts": [
                        {"manual_amount_id": "PMA-2", "created_at": "2026-07-09T00:00:00+00:00"}
                    ],
                }
            ],
        },
    )

    api = bridge.ApiBridge(app_config)

    po_result = api.get_po_detail({"po_id": "PO1"})["data"]
    sc_result = api.get_sc_detail({"sc_id": "SC1"})["data"]
    assert po_result["manual_amounts"][0]["created_at"] != "2026-07-09T00:00:00+00:00"
    assert sc_result["pos"][0]["manual_amounts"][0]["created_at"] != "2026-07-09T00:00:00+00:00"
```

- [ ] **Step 2: Run bridge tests and verify failure**

Run:

```powershell
pytest tests/test_api_bridge.py::test_bridge_manual_amount_methods_forward_payload tests/test_api_bridge.py::test_bridge_formats_manual_amount_timestamps_in_details -q
```

Expected: tests fail because bridge methods and formatting are missing.

- [ ] **Step 3: Format manual amounts in existing detail methods**

In `ApiBridge.get_sc_detail`, change the formatting loop so nested manual amounts are also formatted:

```python
                for key in ("pos", "grs", "operation_records"):
                    if key in result:
                        result[key] = _format_list_timestamps(result[key])
                for po in result.get("pos", []):
                    if isinstance(po, dict) and "manual_amounts" in po:
                        po["manual_amounts"] = _format_list_timestamps(po["manual_amounts"])
```

In `ApiBridge.get_po_detail`, include top-level manual amounts:

```python
                for key in ("manual_amounts", "calloff_scs", "operation_records"):
                    if key in result:
                        result[key] = _format_list_timestamps(result[key])
```

- [ ] **Step 4: Add bridge methods**

Add these methods near the other PO bridge methods:

```python
    def list_po_manual_amounts(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            rows = po_service.list_po_manual_amounts(self.config, current_user, po_id)
            return ok(_format_list_timestamps(rows))
        except Exception as exc:
            return fail(exc)

    def create_po_manual_amount(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            po_id = _require_payload_field(payload, "po_id")
            data = _require_payload_field(payload, "data")
            result = po_service.create_po_manual_amount(self.config, current_user, po_id, data)
            return ok(_format_entity_timestamps(result))
        except Exception as exc:
            return fail(exc)

    def delete_po_manual_amount(self, payload) -> dict:
        try:
            payload = self._required_payload(payload)
            current_user = self._require_current_user()
            manual_amount_id = _require_payload_field(payload, "manual_amount_id")
            return ok(po_service.delete_po_manual_amount(self.config, current_user, manual_amount_id))
        except Exception as exc:
            return fail(exc)
```

- [ ] **Step 5: Run bridge tests and verify pass**

Run:

```powershell
pytest tests/test_api_bridge.py -q
```

Expected: bridge tests pass.

- [ ] **Step 6: Commit**

Run:

```powershell
git add sc_gr_app/api/bridge.py tests/test_api_bridge.py
git commit -m "feat: expose PO manual amount bridge methods"
```

---

### Task 5: Annual Report Integration

**Files:**
- Modify: `sc_gr_app/services/po_service.py`
- Modify: `tests/test_po_annual_report.py`
- Modify: `tests/test_gr_annual_report.py`

- [ ] **Step 1: Add failing annual report tests**

In `_seed` in `tests/test_po_annual_report.py`, add manual rows after the existing GR inserts:

```sql
        INSERT INTO po_manual_amounts (
          manual_amount_id, po_id, year, type, amount, created_by, created_at
        )
        VALUES
          ('PMA-PREV', 'PO_ACTIVE_APPROVED', '2024', 'provision', -10, 'U_REQ', '2025-01-01'),
          ('PMA-TBG', 'PO_ACTIVE_APPROVED', '2025', 'to_be_gr', 222, 'U_REQ', '2025-01-01'),
          ('PMA-OTHER-YEAR', 'PO_ACTIVE_APPROVED', '2026', 'to_be_gr', 999, 'U_REQ', '2025-01-01'),
          ('PMA-OTHER-PO', 'PO_ACTIVE_INDEPENDENT', '2024', 'provision', 333, 'U_REQ', '2025-01-01'),
          ('PMA-DRAFT-ONLY', 'PO_DRAFT_ONLY', '2024', 'provision', 444, 'U_REQ', '2025-01-01');
```

In `test_po_annual_report_maps_amounts_and_blank_columns`, change the manual column assertions to:

```python
    assert row["previous_year_provision"] == -10
    assert row["selected_year_to_be_gr"] == 222
    assert row["selected_year_fc_gr"] == ""
    assert row["remark"] == ""
```

Add this assertion to `test_po_annual_report_includes_qualifying_po_rows_and_sc_only_rows`:

```python
    assert sc_rows["SC-APP-002"]["previous_year_provision"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_to_be_gr"] == ""
    assert "PO-DRAFT-ONLY" not in po_rows
```

Add this test:

```python
def test_po_annual_report_manual_records_do_not_expand_selection_scope(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)
    independent = _by_po(rows)["PO-ACT-FC"]
    po_rows = _by_po(rows)
    sc_rows = _by_sc(rows)

    assert independent["previous_year_provision"] == 333
    assert independent["selected_year_to_be_gr"] == ""
    assert "PO-DRAFT-ONLY" not in po_rows
    assert sc_rows["SC-APP-002"]["previous_year_provision"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_to_be_gr"] == ""
```

Add a GR annual report guard in `tests/test_gr_annual_report.py`. Insert one manual amount for the sample PO after `sample_data` is created, then assert the existing GR annual report output is unchanged:

```python
def test_gr_annual_report_ignores_po_manual_amounts(app_config, sample_data):
    import sqlite3

    conn = sqlite3.connect(app_config.db_path)
    conn.execute(
        """
        INSERT INTO po_manual_amounts (
          manual_amount_id, po_id, year, type, amount, created_by, created_at
        ) VALUES ('PMA-GR-GUARD', 'po-001', '2026', 'to_be_gr', 999999, 'u1', '2026-07-09')
        """
    )
    conn.commit()
    conn.close()

    rows = get_annual_report_data(
        app_config,
        "2026",
        {"role": "admin", "user_id": "u1", "machine_id": "M000001"},
    )

    assert {row["gr_no"] for row in rows} == {"GR-001", "GR-002"}
    assert all("selected_year_to_be_gr" not in row for row in rows)
    assert all("previous_year_provision" not in row for row in rows)
```

- [ ] **Step 2: Run annual report tests and verify failure**

Run:

```powershell
pytest tests/test_po_annual_report.py tests/test_gr_annual_report.py -q
```

Expected: tests fail because manual amount columns are still hard-coded blanks.

- [ ] **Step 3: Join manual amounts by internal PO id**

In `get_annual_report_data`, extend the CTE block with `manual_amounts`:

```sql
            with gr_totals as (
              ...
            ),
            manual_amounts as (
              select
                po_id,
                max(case when year = ? and type = 'provision' then amount end) as previous_year_provision,
                max(case when year = ? and type = 'to_be_gr' then amount end) as selected_year_to_be_gr
              from po_manual_amounts
              where (year = ? and type = 'provision')
                 or (year = ? and type = 'to_be_gr')
              group by po_id
            )
```

In the PO select list, replace:

```sql
              '' as previous_year_provision,
              coalesce(gr.selected_year_gr, 0) as selected_year_gr,
              '' as selected_year_to_be_gr,
```

with:

```sql
              case when ma.previous_year_provision is null then '' else ma.previous_year_provision end as previous_year_provision,
              coalesce(gr.selected_year_gr, 0) as selected_year_gr,
              case when ma.selected_year_to_be_gr is null then '' else ma.selected_year_to_be_gr end as selected_year_to_be_gr,
```

Add the join:

```sql
            left join manual_amounts ma on ma.po_id = po.po_id
```

Update the `conn.execute` parameter tuple to include manual amount years before the existing finished-year parameter:

```python
            (
                previous_year,
                selected_year,
                selected_year,
                previous_year,
                selected_year,
                previous_year,
                selected_year,
                selected_year,
            ),
```

Do not expose `po.po_id` in the final row shape.

- [ ] **Step 4: Run annual report tests and verify pass**

Run:

```powershell
pytest tests/test_po_annual_report.py -q
```

Expected: annual report tests pass, SC-only rows keep manual columns blank, manual-only POs do not enter the PO annual report, and GR annual report output stays unchanged.

- [ ] **Step 5: Commit**

Run:

```powershell
git add sc_gr_app/services/po_service.py tests/test_po_annual_report.py tests/test_gr_annual_report.py
git commit -m "feat: include manual amounts in PO annual report"
```

---

### Task 6: Frontend PO Detail UI

**Files:**
- Modify: `frontend/src/composables/usePo.js`
- Modify: `frontend/src/views/PoDetailView.vue`
- Modify: `frontend/src/i18n/locales/en-US.js`
- Modify: `frontend/src/i18n/locales/zh-CN.js`

- [ ] **Step 1: Add composable bridge helpers**

In `frontend/src/composables/usePo.js`, add these functions alongside existing PO API functions:

```js
async function listPoManualAmounts(poId) {
  return callApi('list_po_manual_amounts', { po_id: poId })
}

async function createPoManualAmount(poId, data) {
  return callApi('create_po_manual_amount', { po_id: poId, data })
}

async function deletePoManualAmount(manualAmountId) {
  return callApi('delete_po_manual_amount', { manual_amount_id: manualAmountId })
}
```

Return them from `usePo()`:

```js
return {
  state,
  searchPos,
  createPo,
  updatePo,
  submitPo,
  finishPo,
  listPoManualAmounts,
  createPoManualAmount,
  deletePoManualAmount,
  setFilters,
  resetFilters,
  onSortChange,
  onPageChange,
  onPageSizeChange,
}
```

Keep the existing returned names intact.

- [ ] **Step 2: Add translations**

Add these flat keys under the existing `po` namespace in `frontend/src/i18n/locales/en-US.js`:

```js
manualAnnualAmounts: 'Manual Annual Amounts',
addManualAmount: 'Add Record',
manualAmountYear: 'Year',
manualAmountType: 'Type',
manualAmountAmount: 'Amount',
manualAmountCreatedBy: 'Created By',
manualAmountCreatedAt: 'Created At',
manualAmountProvision: 'Provision',
manualAmountToBeGr: 'To be GR',
deleteManualAmountConfirm: 'Delete {year} {type} manual amount {amount}?',
manualAmountSaved: 'Manual annual amount saved',
manualAmountDeleted: 'Manual annual amount deleted',
manualAmountNoRecords: 'No manual annual amount records',
manualAmountInvalidYear: 'Year must be four digits',
manualAmountAmountRequired: 'Amount is required',
manualAmountRefreshFailed: 'Saved, but refresh failed. Refresh the detail page to see the latest records.',
```

Add the matching Chinese keys under `po` in `frontend/src/i18n/locales/zh-CN.js`:

```js
manualAnnualAmounts: '手工年度金额',
addManualAmount: '新增记录',
manualAmountYear: '年份',
manualAmountType: '类型',
manualAmountAmount: '金额',
manualAmountCreatedBy: '记录人',
manualAmountCreatedAt: '记录时间',
manualAmountProvision: 'Provision',
manualAmountToBeGr: 'To be GR',
deleteManualAmountConfirm: '确认删除 {year} {type} 手工年度金额 {amount}？',
manualAmountSaved: '手工年度金额已保存',
manualAmountDeleted: '手工年度金额已删除',
manualAmountNoRecords: '暂无手工年度金额记录',
manualAmountInvalidYear: '年份必须是四位数字',
manualAmountAmountRequired: '金额必填',
manualAmountRefreshFailed: '已保存，但刷新失败。请刷新详情页查看最新记录。',
```

Keep the locale file's existing UTF-8 Chinese text style; do not paste mojibake text.

- [ ] **Step 3: Add state and handlers in `PoDetailView.vue`**

In the script section, update the Vue and icon imports:

```js
import { ref, reactive, computed, onMounted, onUnmounted, watch } from 'vue'
import { Plus, Download, Message, Delete } from '@element-plus/icons-vue'
```

Extend the existing `usePo()` destructuring:

```js
const {
  updatePo,
  finishPo,
  submitPo,
  createPoManualAmount,
  deletePoManualAmount,
} = usePo()
```

Add computed manual records that works for both route modes:

```js
const manualAmounts = computed(() => {
  if (poDetail.value?.manual_amounts) return poDetail.value.manual_amounts
  return po.value?.manual_amounts || []
})

const canManagePoManualAmounts = computed(() => {
  if (hasSc.value) return Boolean(po.value?.can_manage_po_manual_amounts)
  return Boolean(
    po.value?.can_manage_po_manual_amounts
    || permissions.value?.can_manage_po_manual_amounts
  )
})
```

Add dialog state:

```js
const manualAmountDialogVisible = ref(false)
const manualAmountSaving = ref(false)
const manualAmountForm = reactive({
  year: new Date().getFullYear().toString(),
  type: 'to_be_gr',
  amount: 0,
})
const manualAmountFormRef = ref(null)
const manualAmountRules = {
  year: [
    {
      validator: (_rule, value, callback) => {
        if (!/^\d{4}$/.test(String(value || ''))) {
          callback(new Error(t('po.manualAmountInvalidYear')))
          return
        }
        callback()
      },
      trigger: 'blur',
    },
  ],
  type: [{ required: true, trigger: 'change' }],
  amount: [
    {
      validator: (_rule, value, callback) => {
        if (value === null || value === undefined || value === '') {
          callback(new Error(t('po.manualAmountAmountRequired')))
          return
        }
        callback()
      },
      trigger: 'change',
    },
  ],
}
```

Add helpers:

```js
function openManualAmountDialog() {
  manualAmountForm.year = new Date().getFullYear().toString()
  manualAmountForm.type = 'to_be_gr'
  manualAmountForm.amount = 0
  manualAmountDialogVisible.value = true
}

function manualAmountTypeLabel(type) {
  return type === 'provision'
    ? t('po.manualAmountProvision')
    : t('po.manualAmountToBeGr')
}

async function refreshPoDetailAfterManualAmountChange() {
  await refreshDetail()
}

async function saveManualAmount() {
  try {
    await manualAmountFormRef.value?.validate()
  } catch {
    return
  }
  manualAmountSaving.value = true
  try {
    await createPoManualAmount(po.value.po_id, {
      year: manualAmountForm.year,
      type: manualAmountForm.type,
      amount: manualAmountForm.amount,
    })
    manualAmountDialogVisible.value = false
    try {
      await refreshPoDetailAfterManualAmountChange()
      ElMessage.success(t('po.manualAmountSaved'))
    } catch (refreshError) {
      ElMessage.warning(t('po.manualAmountRefreshFailed'))
    }
  } catch (error) {
    ElMessage.error(error.message || String(error))
  } finally {
    manualAmountSaving.value = false
  }
}

async function removeManualAmount(row) {
  try {
    await ElMessageBox.confirm(
      t('po.deleteManualAmountConfirm', {
        year: row.year,
        type: manualAmountTypeLabel(row.type),
        amount: row.amount,
      }),
      t('common.confirm'),
      { type: 'warning' }
    )
    await deletePoManualAmount(row.manual_amount_id)
    try {
      await refreshPoDetailAfterManualAmountChange()
      ElMessage.success(t('po.manualAmountDeleted'))
    } catch (refreshError) {
      ElMessage.warning(t('po.manualAmountRefreshFailed'))
    }
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') {
      ElMessage.error(error.message || String(error))
    }
  }
}
```

- [ ] **Step 4: Add the detail-only section template**

Add this section near the other PO detail sections, not in PO lists or dashboards:

```vue
<div class="section-card">
  <div class="section-header">
    <h3>{{ $t('po.manualAnnualAmounts') }}</h3>
    <el-button
      v-if="canManagePoManualAmounts"
      type="primary"
      size="small"
      :disabled="loadingState.count > 0"
      @click="openManualAmountDialog"
    >
      <el-icon><Plus /></el-icon>
      {{ $t('po.addManualAmount') }}
    </el-button>
  </div>
  <el-table :data="manualAmounts" border stripe>
    <el-table-column prop="year" :label="$t('po.manualAmountYear')" width="90" />
    <el-table-column :label="$t('po.manualAmountType')" width="140">
      <template #default="{ row }">
        {{ manualAmountTypeLabel(row.type) }}
      </template>
    </el-table-column>
    <el-table-column :label="$t('po.manualAmountAmount')" width="140" align="right">
      <template #default="{ row }">
        <AmountDisplay :value="row.amount" />
      </template>
    </el-table-column>
    <el-table-column prop="created_by_name" :label="$t('po.manualAmountCreatedBy')" min-width="140" show-overflow-tooltip />
    <el-table-column prop="created_at" :label="$t('po.manualAmountCreatedAt')" min-width="160" />
    <el-table-column
      v-if="canManagePoManualAmounts"
      :label="$t('common.actions')"
      width="90"
      fixed="right"
    >
      <template #default="{ row }">
        <el-button
          type="danger"
          link
          size="small"
          :disabled="loadingState.count > 0"
          @click="removeManualAmount(row)"
        >
          <el-icon><Delete /></el-icon>
        </el-button>
      </template>
    </el-table-column>
    <template #empty>
      <el-empty :description="$t('po.manualAmountNoRecords')" />
    </template>
  </el-table>
</div>
```

Add the dialog:

```vue
<el-dialog
  v-model="manualAmountDialogVisible"
  :title="$t('po.addManualAmount')"
  width="420px"
>
  <el-form
    ref="manualAmountFormRef"
    :model="manualAmountForm"
    :rules="manualAmountRules"
    label-position="top"
  >
    <el-form-item prop="year" :label="$t('po.manualAmountYear')">
      <el-input v-model="manualAmountForm.year" maxlength="4" />
    </el-form-item>
    <el-form-item prop="type" :label="$t('po.manualAmountType')">
      <el-select v-model="manualAmountForm.type" style="width: 100%">
        <el-option :label="$t('po.manualAmountProvision')" value="provision" />
        <el-option :label="$t('po.manualAmountToBeGr')" value="to_be_gr" />
      </el-select>
    </el-form-item>
    <el-form-item prop="amount" :label="$t('po.manualAmountAmount')">
      <el-input-number
        v-model="manualAmountForm.amount"
        :precision="2"
        :step="1000"
        style="width: 100%"
      />
    </el-form-item>
  </el-form>
  <template #footer>
    <el-button :disabled="manualAmountSaving" @click="manualAmountDialogVisible = false">
      {{ $t('common.cancel') }}
    </el-button>
    <el-button
      type="primary"
      :loading="manualAmountSaving"
      :disabled="loadingState.count > 0"
      @click="saveManualAmount"
    >
      {{ $t('common.save') }}
    </el-button>
  </template>
</el-dialog>
```

Ensure `AmountDisplay` is imported or reuse the existing import if already present in `PoDetailView.vue`.

- [ ] **Step 5: Run frontend build**

Run:

```powershell
cd frontend
npm.cmd run build
```

Expected: production build passes.

- [ ] **Step 6: Commit**

Run:

```powershell
git add frontend/src/composables/usePo.js frontend/src/views/PoDetailView.vue frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: manage PO manual amounts in detail view"
```

---

### Task 7: Final Verification and Guard Rails

**Files:**
- No planned source edits unless verification exposes a defect.

- [ ] **Step 1: Run focused backend tests**

Run:

```powershell
pytest tests/test_migrations.py tests/test_po_manual_amounts.py tests/test_po_annual_report.py tests/test_gr_annual_report.py tests/test_api_bridge.py -q
```

Expected: all selected tests pass.

- [ ] **Step 2: Run full backend tests**

Run:

```powershell
pytest -q
```

Expected: all backend tests pass.

- [ ] **Step 3: Run frontend build**

Run:

```powershell
cd frontend
npm.cmd run build
```

Expected: build exits successfully.

- [ ] **Step 4: Inspect for forbidden side effects**

Run:

```powershell
rg -n "po_manual_amounts|create_po_manual_amount|delete_po_manual_amount|can_manage_po_manual_amounts|write_operation_record|notification_service|queue_status_change|_auto_open_outlook_draft|open_entity_email|generate_email_draft|open_email_draft_in_outlook|sender" sc_gr_app frontend/src tests
```

Expected:

- `po_manual_amounts` appears in migrations, PO/SC service cleanup/detail/report code, and tests.
- `create_po_manual_amount` and `delete_po_manual_amount` appear only in PO service, API bridge, frontend PO detail/usePo, and tests.
- `can_manage_po_manual_amounts` appears in permission payloads and frontend visibility checks.
- No manual amount create/delete path calls `write_operation_record`, `notification_service`, `queue_status_change`, `_auto_open_outlook_draft`, `open_entity_email`, `generate_email_draft`, `open_email_draft_in_outlook`, or `sender`.

- [ ] **Step 5: Inspect annual export columns manually**

Run:

```powershell
pytest tests/test_po_annual_report.py::test_po_annual_report_maps_amounts_and_blank_columns tests/test_po_annual_report.py::test_po_annual_report_missing_manual_amounts_are_blank -q
```

Expected:

- `{previous_year} Provision` reads `type = 'provision'`.
- `{selected_year} to be GR` reads `type = 'to_be_gr'`.
- `{selected_year} FC GR` and `Remark` remain blank.
- SC-only rows keep manual amount fields blank.
- No visible `po_id` column is added to annual report rows.

- [ ] **Step 6: Commit verification-only fixes if needed**

If a verification command exposed a defect and source files were changed, run:

```powershell
git add <changed-files>
git commit -m "fix: complete PO manual amount verification"
```

If no files changed, do not create an empty commit.

---

## Completion Criteria

- Database schema version is 40 and fresh databases create `po_manual_amounts`.
- Manual records can be created, listed, and deleted by admin, owning SC requester for SC-linked POs, and PO requester for independent POs.
- Manual records can be added and deleted for finished POs.
- Other users cannot mutate records, but PO visibility still controls read access.
- PO detail shows top-level `manual_amounts`.
- SC detail attaches `manual_amounts` to each nested PO row.
- Bridge timestamp formatting covers both shapes.
- PO and SC deletion remove related manual records before deleting PO rows.
- PO annual report fills previous-year provision and selected-year to-be-GR from manual records.
- Missing manual records and SC-only rows export blanks.
- Frontend build passes.
- Full backend test suite passes.
