# SC Detail Editing Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build SC draft creation, SC Detail, and admin-only SC/PO/GR editing/status workflows while keeping list pages query-first.

**Architecture:** Implement backend capabilities first: schema migration, service rules, query/detail visibility, and bridge APIs. Then update the static pywebview frontend so lists navigate to a dedicated SC Detail view where SC, PO, and GR operations happen. Each vertical slice is tested before the next slice begins.

**Tech Stack:** Python 3.11, SQLite, pytest, pywebview bridge, vanilla ES modules, Node `node:test` for focused frontend logic tests.

---

## File Structure

- Modify `sc_gr_app/db/schema.sql`: update canonical schema to include SC `draft` and nullable draft fields.
- Modify `sc_gr_app/db/migrations.py`: add versioned migration support and a v2 SC table rebuild.
- Modify `tests/test_migrations.py`: verify schema version 2, draft status, and nullable SC draft fields.
- Modify `sc_gr_app/services/sc_service.py`: add draft, submit, update, deny, close, visibility, and detail functions.
- Modify `tests/test_sc_po_gr_flow.py`: extend service coverage for SC draft/detail/status and PO/GR admin workflows.
- Modify `sc_gr_app/services/po_service.py`: make write operations admin-only through new update/status methods.
- Modify `sc_gr_app/services/gr_service.py`: make write operations admin-only through new update/cancel behavior.
- Modify `sc_gr_app/services/query_service.py`: enforce draft visibility rules and prevent draft SC leakage in PO/GR searches.
- Modify `tests/test_query_service.py`: verify admin/requester draft visibility.
- Modify `sc_gr_app/api/bridge.py`: expose write/detail APIs.
- Modify `tests/test_api_bridge.py`: cover bridge payload wrapping and permissions for new APIs.
- Modify `sc_gr_app/web/components/state.js`: add route state for SC Detail and focused PO/GR target IDs.
- Modify `sc_gr_app/web/components/tables.js`: support action columns without row drawer behavior.
- Modify `sc_gr_app/web/components/views.js`: reorder columns, add SC creation and SC Detail rendering.
- Modify `sc_gr_app/web/app.js`: route to detail/new SC flows and remove drawer dependency for SC/PO/GR.
- Create `sc_gr_app/web/components/forms.js`: reusable form collection, validation display, and action button rendering helpers.
- Create `tests/web_table_actions.test.mjs`: focused frontend tests for table column/action behavior.
- Create `tests/web_sc_detail_state.test.mjs`: focused frontend tests for detail route state and action metadata.

## Task 1: Schema Migration For Draft SC

**Files:**
- Modify: `sc_gr_app/db/schema.sql`
- Modify: `sc_gr_app/db/migrations.py`
- Test: `tests/test_migrations.py`

- [ ] **Step 1: Write failing migration tests**

Add these tests to `tests/test_migrations.py`:

```python
def test_migration_records_version_two(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        versions = [
            row[0]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            )
        ]

    assert versions == [1, 2]


def test_sc_records_supports_draft_and_nullable_business_fields(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, description,
              created_by, created_at, updated_at, approved_by, approved_at, closed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SC_DRAFT",
                None,
                "U1",
                None,
                None,
                None,
                None,
                None,
                "draft",
                None,
                "U1",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
                None,
                None,
                None,
            ),
        )
        row = conn.execute(
            "select status, request_type, sc_amount from sc_records where sc_id = 'SC_DRAFT'"
        ).fetchone()

    assert row == ("draft", None, None)
```

- [ ] **Step 2: Run migration tests and verify they fail**

Run: `uv run pytest tests/test_migrations.py -q`

Expected: failures because `SCHEMA_VERSION` is still 1 and `draft`/nullable SC fields are not supported.

- [ ] **Step 3: Update canonical schema**

In `sc_gr_app/db/schema.sql`, change `sc_records`:

```sql
  request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
  cost_center INTEGER,
  sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
  service_period_start TEXT,
  service_period_end TEXT,
  status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'denied', 'closed')),
```

Keep `requester_id`, `created_by`, `created_at`, and `updated_at` as `NOT NULL`.

- [ ] **Step 4: Implement versioned migrations**

Replace `sc_gr_app/db/migrations.py` with a versioned migration structure:

```python
from datetime import datetime, timezone
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect


SCHEMA_VERSION = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _applied_versions(conn) -> set[int]:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
          version INTEGER PRIMARY KEY,
          applied_at TEXT NOT NULL
        );
        """
    )
    return {
        row["version"]
        for row in conn.execute("select version from schema_migrations")
    }


def _record(conn, version: int) -> None:
    conn.execute(
        "insert or ignore into schema_migrations(version, applied_at) values (?, ?)",
        (version, utc_now()),
    )


def _migrate_v1(conn) -> None:
    schema_path = Path(__file__).with_name("schema.sql")
    conn.executescript(schema_path.read_text(encoding="utf-8"))
    _record(conn, 1)


def _migrate_v2(conn) -> None:
    columns = {
        row["name"]: row
        for row in conn.execute("PRAGMA table_info(sc_records)")
    }
    status_sql = conn.execute(
        "select sql from sqlite_master where type='table' and name='sc_records'"
    ).fetchone()["sql"]
    if "draft" in status_sql and columns["request_type"]["notnull"] == 0:
        _record(conn, 2)
        return

    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("ALTER TABLE sc_records RENAME TO sc_records_old")
    conn.execute(
        """
        CREATE TABLE sc_records (
          sc_id TEXT PRIMARY KEY,
          sc_no TEXT,
          requester_id TEXT NOT NULL REFERENCES users(user_id),
          request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
          cost_center INTEGER,
          sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
          service_period_start TEXT,
          service_period_end TEXT,
          status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'denied', 'closed')),
          description TEXT,
          created_by TEXT NOT NULL REFERENCES users(user_id),
          created_at TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          approved_by TEXT REFERENCES users(user_id),
          approved_at TEXT,
          closed_at TEXT
        )
        """
    )
    conn.execute(
        """
        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at, approved_by, approved_at, closed_at
        )
        SELECT
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at, approved_by, approved_at, closed_at
        FROM sc_records_old
        """
    )
    conn.execute("DROP TABLE sc_records_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_requester ON sc_records(requester_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sc_records_status ON sc_records(status)")
    conn.execute("PRAGMA foreign_keys = ON")
    _record(conn, 2)


def migrate(config: AppConfig) -> None:
    with connect(config) as conn:
        try:
            conn.execute("BEGIN")
            applied = _applied_versions(conn)
            if 1 not in applied:
                _migrate_v1(conn)
            if 2 not in _applied_versions(conn):
                _migrate_v2(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
```

- [ ] **Step 5: Update existing migration version test**

Change `test_migration_records_version_once` to expect two versions:

```python
def test_migration_records_versions_once(app_config):
    migrate(app_config)
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        rows = conn.execute(
            "select version, applied_at from schema_migrations order by version"
        ).fetchall()

    assert [row[0] for row in rows] == [1, 2]
    assert rows[0][1]
    assert rows[1][1]
```

- [ ] **Step 6: Run migration tests**

Run: `uv run pytest tests/test_migrations.py -q`

Expected: all migration tests pass.

- [ ] **Step 7: Run full tests**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git add sc_gr_app/db/schema.sql sc_gr_app/db/migrations.py tests/test_migrations.py
git commit -m "feat(db): support draft SC records"
```

## Task 2: SC Draft, Submit, Update, Status, And Detail Services

**Files:**
- Modify: `sc_gr_app/services/sc_service.py`
- Modify: `sc_gr_app/services/query_service.py`
- Test: `tests/test_sc_po_gr_flow.py`
- Test: `tests/test_query_service.py`

- [ ] **Step 1: Add failing SC draft service tests**

Append to `tests/test_sc_po_gr_flow.py`:

```python
OTHER_USER = {"user_id": "U2", "role": "requester", "machine_id": "M3"}


def seed_other_user(app_config):
    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "U2",
                "M3",
                "Other Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_requester_creates_minimal_draft_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft

    created = create_sc_draft(
        app_config,
        USER,
        {"sc_id": "SC_DRAFT", "requester_id": "U1"},
    )

    assert created["status"] == "draft"
    assert created["requester_id"] == "U1"
    assert created["request_type"] is None
    assert created["sc_amount"] is None


def test_requester_cannot_create_draft_for_another_owner(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft

    with pytest.raises(PermissionDenied):
        create_sc_draft(
            app_config,
            USER,
            {"sc_id": "SC_DRAFT", "requester_id": "U2"},
        )


def test_submit_draft_requires_business_fields_but_not_sc_no(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})

    with pytest.raises(ValidationError, match="request_type is required"):
        submit_sc(app_config, USER, "SC_DRAFT", {})

    submitted = submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    assert submitted["status"] == "pending"
    assert submitted["sc_no"] is None


def test_owner_cannot_edit_pending_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc, update_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    with pytest.raises(PermissionDenied):
        update_sc(app_config, USER, "SC_DRAFT", {"description": "late change"})


def test_admin_cannot_approve_sc_without_sc_no(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    with pytest.raises(ConflictError, match="SC No is required"):
        approve_sc(app_config, ADMIN, "SC_DRAFT")


def test_admin_updates_pending_sc_then_approves_denies_and_closes(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import (
        create_sc_draft,
        submit_sc,
        update_sc,
        deny_sc,
        close_sc,
    )

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    updated = update_sc(app_config, ADMIN, "SC_DRAFT", {"sc_no": "SC001"})
    approved = approve_sc(app_config, ADMIN, "SC_DRAFT")
    closed = close_sc(app_config, ADMIN, "SC_DRAFT")

    assert updated["sc_no"] == "SC001"
    assert approved["status"] == "approved"
    assert closed["status"] == "closed"

    create_sc(app_config, USER, {
        "sc_id": "SC_DENY",
        "requester_id": "U1",
        "request_type": "service",
        "cost_center": 1001,
        "sc_amount": 100,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    denied = deny_sc(app_config, ADMIN, "SC_DENY")
    assert denied["status"] == "denied"
```

- [ ] **Step 2: Add failing detail and visibility tests**

Add to `tests/test_query_service.py`:

```python
def test_sc_search_hides_drafts_from_admin_and_other_requesters(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft
    from sc_gr_app.services import query_service

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})

    admin_rows = query_service.search_scs(app_config, current_user=ADMIN, limit=100)
    owner_rows = query_service.search_scs(app_config, current_user=USER, limit=100)
    other_rows = query_service.search_scs(app_config, current_user=OTHER_USER, limit=100)

    assert [row["sc_id"] for row in admin_rows] == []
    assert [row["sc_id"] for row in owner_rows] == ["SC_DRAFT"]
    assert [row["sc_id"] for row in other_rows] == []
```

If `tests/test_query_service.py` does not import `USER`, `ADMIN`, and helpers, duplicate the constants in that file to keep tests independent.

- [ ] **Step 3: Run focused tests and verify failure**

Run:

```powershell
uv run pytest tests/test_sc_po_gr_flow.py tests/test_query_service.py -q
```

Expected: import/signature failures for new SC functions and `current_user` query parameter.

- [ ] **Step 4: Implement SC helper functions**

In `sc_gr_app/services/sc_service.py`, add:

```python
OPTIONAL_UPDATE_FIELDS = (
    "sc_no",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
    "description",
)


def _require_submit_fields(data: dict) -> None:
    _require_fields(
        data,
        (
            "request_type",
            "cost_center",
            "sc_amount",
            "service_period_start",
            "service_period_end",
        ),
    )
    if data["request_type"] not in SUPPORTED_REQUEST_TYPES:
        raise ValidationError("request_type is invalid")
    _positive_number(data["sc_amount"], "sc_amount")
    if data["service_period_start"] > data["service_period_end"]:
        raise ValidationError("service period is invalid")


def _assert_can_view_sc(user: dict, sc: dict) -> None:
    if sc["status"] == "draft":
        if user.get("role") != "requester" or user.get("user_id") != sc["requester_id"]:
            raise PermissionDenied("SC is not visible")
        return
    if user.get("role") == "admin":
        return
    if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
        return
    raise PermissionDenied("SC is not visible")


def _assert_can_edit_sc(user: dict, sc: dict) -> None:
    if sc["status"] == "draft":
        if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
            return
        raise PermissionDenied("Only the draft owner can edit this SC")
    if sc["status"] == "closed":
        raise ConflictError("Closed SC cannot be edited")
    if user.get("role") == "admin":
        return
    raise PermissionDenied("Admin permission required")
```

- [ ] **Step 5: Implement SC draft/submit/update/status/detail methods**

In `sc_gr_app/services/sc_service.py`, add these functions. They can use the helper functions from Step 4, existing `_get_sc`, `_positive_number`, `utc_now`, and `write_audit_log`.

```python
def create_sc_draft(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, ("sc_id", "requester_id"))
    if current_user["role"] == "requester" and data["requester_id"] != current_user["user_id"]:
        raise PermissionDenied("Requester can only create their own draft SC")

    timestamp = utc_now()
    sc_id = data["sc_id"]
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    insert into sc_records (
                      sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
                      service_period_start, service_period_end, status, description,
                      created_by, created_at, updated_at, approved_by, approved_at, closed_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sc_id,
                        data.get("sc_no"),
                        data["requester_id"],
                        data.get("request_type"),
                        data.get("cost_center"),
                        float(data["sc_amount"]) if data.get("sc_amount") not in (None, "") else None,
                        data.get("service_period_start"),
                        data.get("service_period_end"),
                        "draft",
                        data.get("description"),
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                        None,
                        None,
                        None,
                    ),
                )
                created = _get_sc(conn, sc_id)
                write_audit_log(conn, action_type="create_sc_draft", object_type="sc", object_id=sc_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=None, after=created)
                conn.commit()
                return created
            except Exception:
                conn.rollback()
                raise


def submit_sc(config: AppConfig, current_user: dict, sc_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "draft":
                    raise ConflictError("SC must be draft")
                if current_user["role"] != "requester" or before["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the draft owner can submit this SC")
                merged = {**before, **data}
                _require_submit_fields(merged)
                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set sc_no = ?, request_type = ?, cost_center = ?, sc_amount = ?,
                        service_period_start = ?, service_period_end = ?, description = ?,
                        status = 'pending', updated_at = ?
                    where sc_id = ?
                    """,
                    (
                        merged.get("sc_no"),
                        merged["request_type"],
                        merged["cost_center"],
                        float(merged["sc_amount"]),
                        merged["service_period_start"],
                        merged["service_period_end"],
                        merged.get("description"),
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(conn, action_type="submit_sc", object_type="sc", object_id=sc_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def update_sc(config: AppConfig, current_user: dict, sc_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    allowed = {key: value for key, value in data.items() if key in OPTIONAL_UPDATE_FIELDS}
    if not allowed:
        raise ValidationError("No SC fields to update")
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                _assert_can_edit_sc(current_user, before)
                merged = {**before, **allowed}
                if merged.get("request_type") not in (None, "") and merged["request_type"] not in SUPPORTED_REQUEST_TYPES:
                    raise ValidationError("request_type is invalid")
                if merged.get("sc_amount") not in (None, ""):
                    _positive_number(merged["sc_amount"], "sc_amount")
                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set sc_no = ?, request_type = ?, cost_center = ?, sc_amount = ?,
                        service_period_start = ?, service_period_end = ?, description = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (
                        merged.get("sc_no"),
                        merged.get("request_type"),
                        merged.get("cost_center"),
                        float(merged["sc_amount"]) if merged.get("sc_amount") not in (None, "") else None,
                        merged.get("service_period_start"),
                        merged.get("service_period_end"),
                        merged.get("description"),
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(conn, action_type="update_sc", object_type="sc", object_id=sc_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def deny_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_admin(current_user)
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "pending":
                    raise ConflictError("SC must be pending")
                timestamp = utc_now()
                conn.execute("update sc_records set status = 'denied', updated_at = ? where sc_id = ?", (timestamp, sc_id))
                after = _get_sc(conn, sc_id)
                write_audit_log(conn, action_type="deny_sc", object_type="sc", object_id=sc_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def close_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_admin(current_user)
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "approved":
                    raise ConflictError("SC must be approved")
                timestamp = utc_now()
                conn.execute(
                    "update sc_records set status = 'closed', closed_at = ?, updated_at = ? where sc_id = ?",
                    (timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(conn, action_type="close_sc", object_type="sc", object_id=sc_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def get_sc_detail(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    with connect(config) as conn:
        sc = _get_sc(conn, sc_id)
        _assert_can_view_sc(current_user, sc)
        pos = [dict(row) for row in conn.execute("select * from pos where sc_id = ? order by created_at, po_id", (sc_id,))]
        grs = [
            dict(row)
            for row in conn.execute(
                """
                select gr.*
                from gr_requests gr
                join pos po on po.po_id = gr.po_id
                where po.sc_id = ?
                order by gr.created_at, gr.gr_id
                """,
                (sc_id,),
            )
        ]
        audit_logs = [dict(row) for row in conn.execute("select * from audit_logs where sc_id = ? order by created_at desc", (sc_id,))]
    return {
        "sc": sc,
        "budget": compute_sc_budget(config, sc_id),
        "pos": pos,
        "grs": grs,
        "audit_logs": audit_logs,
        "permissions": _sc_permissions(current_user, sc),
    }
```

Implementation rules:

- Use `LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"])`.
- Wrap writes in `BEGIN IMMEDIATE` and rollback on errors.
- Use `_get_sc(conn, sc_id)` before and after writes.
- Use `write_audit_log` for `create_sc_draft`, `submit_sc`, `update_sc`, `deny_sc`, and `close_sc`.
- In `approve_sc`, add:

```python
if not before["sc_no"]:
    raise ConflictError("SC No is required")
```

- For `get_sc_detail`, return:

```python
{
    "sc": sc,
    "budget": compute_sc_budget(config, sc_id),
    "pos": pos,
    "grs": grs,
    "audit_logs": audit_logs,
    "permissions": {
        "can_edit_sc": bool,
        "can_submit_sc": bool,
        "can_approve_sc": bool,
        "can_deny_sc": bool,
        "can_close_sc": bool,
        "can_manage_po": bool,
        "can_manage_gr": bool,
    },
}
```

- [ ] **Step 6: Adjust query visibility**

Modify `search_scs`, `search_pos`, and `search_grs` in `sc_gr_app/services/query_service.py` to accept `current_user: dict | None = None`.

For `search_scs`, append visibility clauses:

```python
if current_user:
    if current_user.get("role") == "admin":
        clauses.append("sc.status != 'draft'")
    elif current_user.get("role") == "requester":
        clauses.append("sc.requester_id = ?")
        params.append(current_user["user_id"])
    else:
        raise ValidationError("current_user is invalid")
```

For `search_pos` and `search_grs`, always exclude draft parent SC records:

```sql
where sc.status != 'draft'
```

Integrate that condition into the existing generic `_search` path by passing `base_clauses` or by adding explicit clauses before text/filter clauses.

- [ ] **Step 7: Run focused tests**

Run:

```powershell
uv run pytest tests/test_sc_po_gr_flow.py tests/test_query_service.py -q
```

Expected: focused tests pass.

- [ ] **Step 8: Run full tests**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 9: Commit**

```powershell
git add sc_gr_app/services/sc_service.py sc_gr_app/services/query_service.py tests/test_sc_po_gr_flow.py tests/test_query_service.py
git commit -m "feat(services): add SC draft and detail workflow"
```

## Task 3: PO Admin Update And Status Services

**Files:**
- Modify: `sc_gr_app/services/po_service.py`
- Test: `tests/test_sc_po_gr_flow.py`

- [ ] **Step 1: Write failing PO tests**

Append to `tests/test_sc_po_gr_flow.py`:

```python
def test_po_writes_require_admin(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    from sc_gr_app.services.po_service import approve_po, finish_po, update_po

    with pytest.raises(PermissionDenied):
        update_po(app_config, USER, "PO1", {"po_no": "PO002"})
    with pytest.raises(PermissionDenied):
        approve_po(app_config, USER, "PO1")
    with pytest.raises(PermissionDenied):
        finish_po(app_config, USER, "PO1")


def test_admin_updates_po_with_budget_validation(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_amount=800)
    create_gr(app_config, USER, {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 300})

    from sc_gr_app.services.po_service import update_po

    with pytest.raises(ConflictError, match="below GR usage"):
        update_po(app_config, ADMIN, "PO1", {"po_amount": 299})

    updated = update_po(
        app_config,
        ADMIN,
        "PO1",
        {
            "po_no": "PO002",
            "po_amount": 500,
            "contract_no": "CTR-001",
            "payment_frequency": "monthly",
        },
    )

    assert updated["po_no"] == "PO002"
    assert updated["po_amount"] == 500
    assert updated["contract_no"] == "CTR-001"


def test_admin_approves_and_finishes_po(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_status="po_pending")

    from sc_gr_app.services.po_service import approve_po, finish_po

    approved = approve_po(app_config, ADMIN, "PO1")
    finished = finish_po(app_config, ADMIN, "PO1")

    assert approved["status"] == "po_approved"
    assert finished["status"] == "finished"
```

- [ ] **Step 2: Run PO tests and verify failure**

Run:

```powershell
uv run pytest tests/test_sc_po_gr_flow.py -q
```

Expected: import failures for `update_po`, `approve_po`, and `finish_po`, plus create permissions still allow requester.

- [ ] **Step 3: Make PO writes admin-only**

In `sc_gr_app/services/po_service.py`:

- Import `require_admin`.
- Change `create_po` from `require_requester_or_admin(current_user)` to `require_admin(current_user)`.
- Update any existing tests that create PO through `USER` to use `ADMIN`.

- [ ] **Step 4: Implement PO update/status methods**

Add:

```python
def _get_po_or_raise(conn, po_id: str) -> dict:
    row = conn.execute("select * from pos where po_id = ?", (po_id,)).fetchone()
    if row is None:
        raise NotFound(f"PO not found: {po_id}")
    return _row_to_dict(row)


def _po_gr_usage(conn, po_id: str) -> Decimal:
    row = conn.execute(
        """
        select
          coalesce(sum(case when status = 'pending' then estimated_amount else 0 end), 0)
          + coalesce(sum(case when status = 'approved' then con_value else 0 end), 0)
          as used
        from gr_requests
        where po_id = ?
        """,
        (po_id,),
    ).fetchone()
    return Decimal(str(row["used"]))
```

Implement these methods:

```python
def update_po(config: AppConfig, current_user: dict, po_id: str, data: dict) -> dict:
    require_admin(current_user)
    allowed_fields = {
        "vendor_id",
        "po_no",
        "po_amount",
        "contract_from",
        "contract_to",
        "contract_no",
        "payment_frequency",
    }
    updates = {key: value for key, value in data.items() if key in allowed_fields}
    if not updates:
        raise ValidationError("No PO fields to update")
    with connect(config) as lookup_conn:
        before_lookup = _get_po_or_raise(lookup_conn, po_id)
        sc_id = before_lookup["sc_id"]
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                sc = conn.execute("select * from sc_records where sc_id = ?", (before["sc_id"],)).fetchone()
                if sc["status"] == "closed":
                    raise ConflictError("Closed SC cannot be edited")
                merged = {**before, **updates}
                po_amount = _positive_number(merged["po_amount"], "po_amount")
                if po_amount < _po_gr_usage(conn, po_id):
                    raise ConflictError("PO amount cannot be below GR usage")
                if merged["vendor_id"] != before["vendor_id"]:
                    vendor = conn.execute("select vendor_id from vendors where vendor_id = ?", (merged["vendor_id"],)).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {merged['vendor_id']}")
                sibling_total = Decimal(str(conn.execute("select coalesce(sum(po_amount), 0) as total from pos where sc_id = ? and po_id != ?", (before["sc_id"], po_id)).fetchone()["total"]))
                if sibling_total + po_amount > Decimal(str(sc["sc_amount"])):
                    raise ConflictError("PO total would exceed SC amount")
                timestamp = utc_now()
                conn.execute(
                    """
                    update pos
                    set vendor_id = ?, po_no = ?, po_amount = ?, contract_from = ?,
                        contract_to = ?, contract_no = ?, payment_frequency = ?, updated_at = ?
                    where po_id = ?
                    """,
                    (
                        merged["vendor_id"],
                        merged.get("po_no"),
                        float(po_amount),
                        merged.get("contract_from"),
                        merged.get("contract_to"),
                        merged.get("contract_no"),
                        merged.get("payment_frequency"),
                        timestamp,
                        po_id,
                    ),
                )
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(conn, action_type="update_po", object_type="po", object_id=po_id, sc_id=before["sc_id"], operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def approve_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_admin(current_user)
    with connect(config) as lookup_conn:
        before_lookup = _get_po_or_raise(lookup_conn, po_id)
        sc_id = before_lookup["sc_id"]
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "po_pending":
                    raise ConflictError("PO must be pending")
                timestamp = utc_now()
                conn.execute("update pos set status = 'po_approved', updated_at = ? where po_id = ?", (timestamp, po_id))
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(conn, action_type="approve_po", object_type="po", object_id=po_id, sc_id=before["sc_id"], operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_admin(current_user)
    with connect(config) as lookup_conn:
        before_lookup = _get_po_or_raise(lookup_conn, po_id)
        sc_id = before_lookup["sc_id"]
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "po_approved":
                    raise ConflictError("PO must be approved")
                timestamp = utc_now()
                conn.execute("update pos set status = 'finished', updated_at = ? where po_id = ?", (timestamp, po_id))
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(conn, action_type="finish_po", object_type="po", object_id=po_id, sc_id=before["sc_id"], operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise
```

Rules:

- Lock by parent SC.
- Reject parent SC `closed`.
- Validate vendor exists when `vendor_id` changes.
- Validate `po_amount` is positive when provided.
- Reject new amount below `_po_gr_usage`.
- Reject total PO allocation above SC amount.
- `approve_po` requires `po_pending`.
- `finish_po` requires `po_approved`.
- Audit actions: `update_po`, `approve_po`, `finish_po`.

- [ ] **Step 5: Update tests that still create PO with requester**

Search:

```powershell
rg "create_po\\(" tests -n
```

For service tests that are not testing permission denial, use `ADMIN` as the current user.

- [ ] **Step 6: Run focused tests**

Run: `uv run pytest tests/test_sc_po_gr_flow.py -q`

Expected: focused tests pass.

- [ ] **Step 7: Run full tests**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 8: Commit**

```powershell
git add sc_gr_app/services/po_service.py tests/test_sc_po_gr_flow.py
git commit -m "feat(services): add admin PO editing workflow"
```

## Task 4: GR Admin Update And Cancel Services

**Files:**
- Modify: `sc_gr_app/services/gr_service.py`
- Test: `tests/test_sc_po_gr_flow.py`

- [ ] **Step 1: Write failing GR tests**

Append to `tests/test_sc_po_gr_flow.py`:

```python
def test_gr_writes_require_admin(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    from sc_gr_app.services.gr_service import cancel_gr, update_gr

    with pytest.raises(PermissionDenied):
        create_gr(app_config, USER, {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100})

    create_gr(app_config, ADMIN, {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100})

    with pytest.raises(PermissionDenied):
        update_gr(app_config, USER, "GR1", {"remark": "changed"})
    with pytest.raises(PermissionDenied):
        cancel_gr(app_config, USER, "GR1")


def test_admin_updates_pending_gr_with_budget_validation(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=500, po_amount=500)
    create_gr(app_config, ADMIN, {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100})

    from sc_gr_app.services.gr_service import update_gr

    with pytest.raises(ConflictError, match="available amount is insufficient"):
        update_gr(app_config, ADMIN, "GR1", {"estimated_amount": 600})

    updated = update_gr(app_config, ADMIN, "GR1", {"estimated_amount": 200, "remark": "updated"})

    assert updated["estimated_amount"] == 200
    assert updated["remark"] == "updated"


def test_admin_updates_approved_gr_con_value_and_cancels_pending_gr(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(app_config, ADMIN, {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100})
    approve_gr(app_config, ADMIN, "GR1", con_value=90)
    create_gr(app_config, ADMIN, {"gr_id": "GR2", "po_id": "PO1", "estimated_amount": 50})

    from sc_gr_app.services.gr_service import cancel_gr, update_gr

    updated = update_gr(app_config, ADMIN, "GR1", {"con_value": 95, "remark": "invoice adjusted"})
    cancelled = cancel_gr(app_config, ADMIN, "GR2")

    assert updated["con_value"] == 95
    assert updated["remark"] == "invoice adjusted"
    assert cancelled["status"] == "cancelled"
```

- [ ] **Step 2: Run GR tests and verify failure**

Run: `uv run pytest tests/test_sc_po_gr_flow.py -q`

Expected: missing `update_gr`/`cancel_gr` and requester write permissions still too broad.

- [ ] **Step 3: Make GR create admin-only**

In `sc_gr_app/services/gr_service.py`, change `create_gr` from `require_requester_or_admin(current_user)` to `require_admin(current_user)`.

Update non-permission tests so calls shaped like `create_gr(app_config, USER, payload)` become `create_gr(app_config, ADMIN, payload)`. Keep the requester call only in `test_gr_writes_require_admin`, where the test intentionally expects `PermissionDenied`.

- [ ] **Step 4: Implement GR update and cancel**

Add:

```python
def update_gr(config: AppConfig, current_user: dict, gr_id: str, data: dict) -> dict:
    require_admin(current_user)
    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            """
            select po.sc_id
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where gr.gr_id = ?
            """,
            (gr_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"GR not found: {gr_id}")
        sc_id = lookup["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_gr(conn, gr_id)
                if before["status"] == "cancelled":
                    raise ConflictError("Cancelled GR cannot be edited")
                updates = dict(data)
                timestamp = utc_now()
                if before["status"] == "pending":
                    merged = {**before, **{key: updates[key] for key in ("po_id", "requester_id", "estimated_amount", "remark") if key in updates}}
                    amount = _positive_number(merged["estimated_amount"], "estimated_amount")
                    po_sc = _get_po_sc(conn, merged["po_id"])
                    _validate_gr_creation_context(config, po_sc, amount - Decimal(str(before["estimated_amount"])) if merged["po_id"] == before["po_id"] else amount)
                    conn.execute(
                        "update gr_requests set po_id = ?, requester_id = ?, estimated_amount = ?, remark = ? where gr_id = ?",
                        (merged["po_id"], merged["requester_id"], float(amount), merged.get("remark"), gr_id),
                    )
                else:
                    allowed = {key: updates[key] for key in ("con_value", "remark") if key in updates}
                    if not allowed:
                        raise ValidationError("No GR fields to update")
                    merged = {**before, **allowed}
                    con_value = _non_negative_number(merged["con_value"], "con_value")
                    extra_amount = con_value - Decimal(str(before["con_value"]))
                    if extra_amount > 0:
                        sc_budget = compute_sc_budget_decimal(config, sc_id)
                        po_budget = compute_po_budget_decimal(config, before["po_id"])
                        if sc_budget["sc_available_amount"] < extra_amount:
                            raise ConflictError("SC available amount is insufficient")
                        if po_budget["open_po_amount"] < extra_amount:
                            raise ConflictError("PO open amount is insufficient")
                    conn.execute(
                        "update gr_requests set con_value = ?, remark = ? where gr_id = ?",
                        (float(con_value), merged.get("remark"), gr_id),
                    )
                after = _get_gr(conn, gr_id)
                write_audit_log(conn, action_type="update_gr", object_type="gr", object_id=gr_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def cancel_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    require_admin(current_user)
    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            """
            select po.sc_id
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where gr.gr_id = ?
            """,
            (gr_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"GR not found: {gr_id}")
        sc_id = lookup["sc_id"]
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_gr(conn, gr_id)
                if before["status"] != "pending":
                    raise ConflictError("GR must be pending")
                timestamp = utc_now()
                conn.execute(
                    "update gr_requests set status = 'cancelled', cancelled_by = ?, cancelled_at = ? where gr_id = ?",
                    (current_user["user_id"], timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_audit_log(conn, action_type="cancel_gr", object_type="gr", object_id=gr_id, sc_id=sc_id, operator_id=current_user["user_id"], machine_id=current_user["machine_id"], before=before, after=after)
                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise
```

Rules:

- Lookup parent SC by `gr_id`, then lock `sc:{sc_id}`.
- Pending GR may update `po_id`, `requester_id`, `estimated_amount`, and `remark`.
- Approved GR may update `con_value` and `remark`.
- Cancelled GR raises `ConflictError("Cancelled GR cannot be edited")`.
- Updating pending `estimated_amount` revalidates SC and PO available budget using the delta against old estimated amount.
- Updating approved `con_value` revalidates SC and PO available budget using the delta against old con value.
- `cancel_gr` requires status `pending`.
- Audit actions: `update_gr`, `cancel_gr`.

- [ ] **Step 5: Run focused tests**

Run: `uv run pytest tests/test_sc_po_gr_flow.py -q`

Expected: focused tests pass.

- [ ] **Step 6: Run full tests**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```powershell
git add sc_gr_app/services/gr_service.py tests/test_sc_po_gr_flow.py
git commit -m "feat(services): add admin GR editing workflow"
```

## Task 5: Bridge Write And Detail APIs

**Files:**
- Modify: `sc_gr_app/api/bridge.py`
- Test: `tests/test_api_bridge.py`

- [ ] **Step 1: Write failing bridge tests**

Add to `tests/test_api_bridge.py`:

```python
def test_bridge_forwards_sc_detail_and_write_methods(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: {"user_id": "A1", "role": "admin", "machine_id": machine_id},
    )

    calls = []

    def fake(name):
        def _call(config, user, *args):
            calls.append((name, config, user, args))
            return {"name": name}
        return _call

    monkeypatch.setattr(bridge.sc_service, "get_sc_detail", fake("get_sc_detail"))
    monkeypatch.setattr(bridge.sc_service, "create_sc_draft", fake("create_sc_draft"))
    monkeypatch.setattr(bridge.sc_service, "submit_sc", fake("submit_sc"))
    monkeypatch.setattr(bridge.sc_service, "update_sc", fake("update_sc"))
    monkeypatch.setattr(bridge.sc_service, "approve_sc", fake("approve_sc"))
    monkeypatch.setattr(bridge.sc_service, "deny_sc", fake("deny_sc"))
    monkeypatch.setattr(bridge.sc_service, "close_sc", fake("close_sc"))

    api = bridge.ApiBridge(app_config)

    assert api.get_sc_detail({"sc_id": "SC1"})["ok"] is True
    assert api.create_sc_draft({"data": {"sc_id": "SC1"}})["ok"] is True
    assert api.submit_sc({"sc_id": "SC1", "data": {}})["ok"] is True
    assert api.update_sc({"sc_id": "SC1", "data": {}})["ok"] is True
    assert api.approve_sc({"sc_id": "SC1"})["ok"] is True
    assert api.deny_sc({"sc_id": "SC1"})["ok"] is True
    assert api.close_sc({"sc_id": "SC1"})["ok"] is True

    assert [call[0] for call in calls] == [
        "get_sc_detail",
        "create_sc_draft",
        "submit_sc",
        "update_sc",
        "approve_sc",
        "deny_sc",
        "close_sc",
    ]


def test_bridge_forwards_po_and_gr_write_methods(monkeypatch, app_config):
    from sc_gr_app.api import bridge

    monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
    monkeypatch.setattr(
        bridge,
        "get_user_by_machine_id",
        lambda config, machine_id: {"user_id": "A1", "role": "admin", "machine_id": machine_id},
    )

    calls = []

    def fake(name):
        def _call(config, user, *args):
            calls.append((name, args))
            return {"name": name}
        return _call

    monkeypatch.setattr(bridge.po_service, "create_po", fake("create_po"))
    monkeypatch.setattr(bridge.po_service, "update_po", fake("update_po"))
    monkeypatch.setattr(bridge.po_service, "approve_po", fake("approve_po"))
    monkeypatch.setattr(bridge.po_service, "finish_po", fake("finish_po"))
    monkeypatch.setattr(bridge.gr_service, "create_gr", fake("create_gr"))
    monkeypatch.setattr(bridge.gr_service, "update_gr", fake("update_gr"))
    monkeypatch.setattr(bridge.gr_service, "approve_gr", fake("approve_gr"))
    monkeypatch.setattr(bridge.gr_service, "cancel_gr", fake("cancel_gr"))

    api = bridge.ApiBridge(app_config)

    for method, payload in [
        ("create_po", {"data": {}}),
        ("update_po", {"po_id": "PO1", "data": {}}),
        ("approve_po", {"po_id": "PO1"}),
        ("finish_po", {"po_id": "PO1"}),
        ("create_gr", {"data": {}}),
        ("update_gr", {"gr_id": "GR1", "data": {}}),
        ("approve_gr", {"gr_id": "GR1", "con_value": 10}),
        ("cancel_gr", {"gr_id": "GR1"}),
    ]:
        assert getattr(api, method)(payload)["ok"] is True

    assert [call[0] for call in calls] == [
        "create_po",
        "update_po",
        "approve_po",
        "finish_po",
        "create_gr",
        "update_gr",
        "approve_gr",
        "cancel_gr",
    ]
```

- [ ] **Step 2: Run bridge tests and verify failure**

Run: `uv run pytest tests/test_api_bridge.py -q`

Expected: bridge module does not expose/import new services and methods.

- [ ] **Step 3: Import services in bridge**

In `sc_gr_app/api/bridge.py`, change:

```python
from sc_gr_app.services import query_service
```

to:

```python
from sc_gr_app.services import gr_service, po_service, query_service, sc_service
```

- [ ] **Step 4: Add bridge helpers**

Add:

```python
def _require_payload_field(self, payload: dict, field: str):
    if payload.get(field) in (None, ""):
        raise ValidationError(f"{field} is required")
    return payload[field]
```

- [ ] **Step 5: Add SC bridge methods**

Add methods:

```python
def get_sc_detail(self, payload=None) -> dict:
    try:
        payload = self._payload(payload)
        user = self._require_current_user()
        sc_id = self._require_payload_field(payload, "sc_id")
        return ok(sc_service.get_sc_detail(self.config, user, sc_id))
    except Exception as exc:
        return fail(exc)
```

Repeat this pattern for `create_sc_draft`, `submit_sc`, `update_sc`, `approve_sc`, `deny_sc`, and `close_sc`.

- [ ] **Step 6: Add PO and GR bridge methods**

Follow the same wrapper pattern for:

- `create_po`
- `update_po`
- `approve_po`
- `finish_po`
- `create_gr`
- `update_gr`
- `approve_gr`
- `cancel_gr`

- [ ] **Step 7: Pass current_user to searches**

Update existing search methods:

```python
user = self._require_current_user()
return ok(query_service.search_scs(self.config, current_user=user, **payload))
```

Do the same for `search_pos` and `search_grs` so draft visibility is enforced.

- [ ] **Step 8: Run bridge tests**

Run: `uv run pytest tests/test_api_bridge.py -q`

Expected: bridge tests pass.

- [ ] **Step 9: Run full tests**

Run: `uv run pytest`

Expected: all tests pass.

- [ ] **Step 10: Commit**

```powershell
git add sc_gr_app/api/bridge.py tests/test_api_bridge.py
git commit -m "feat(api): expose SC detail editing bridge"
```

## Task 6: Frontend Routing, Table Actions, And Detail State

**Files:**
- Modify: `sc_gr_app/web/components/state.js`
- Modify: `sc_gr_app/web/components/tables.js`
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/app.js`
- Create: `tests/web_table_actions.test.mjs`
- Create: `tests/web_sc_detail_state.test.mjs`

- [ ] **Step 1: Write failing table action tests**

Create `tests/web_table_actions.test.mjs`:

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { getColumnsForView } from "../sc_gr_app/web/components/views.js";

test("SC, PO, and GR list columns put status first and actions last", () => {
  for (const view of ["sc", "po", "gr"]) {
    const columns = getColumnsForView(view);
    assert.equal(columns[0].key, "status");
    assert.equal(columns.at(-1).key, "actions");
  }
});
```

- [ ] **Step 2: Write failing detail state tests**

Create `tests/web_sc_detail_state.test.mjs`:

```javascript
import assert from "node:assert/strict";
import { test } from "node:test";

import { state, setScDetailTarget, clearScDetailTarget } from "../sc_gr_app/web/components/state.js";

test("SC detail target tracks owning SC and optional focused record", () => {
  setScDetailTarget("SC1", { poId: "PO1" });

  assert.equal(state.scDetail.scId, "SC1");
  assert.equal(state.scDetail.poId, "PO1");
  assert.equal(state.scDetail.grId, null);

  setScDetailTarget("SC1", { grId: "GR1" });

  assert.equal(state.scDetail.poId, null);
  assert.equal(state.scDetail.grId, "GR1");

  clearScDetailTarget();

  assert.equal(state.scDetail.scId, null);
  assert.equal(state.scDetail.poId, null);
  assert.equal(state.scDetail.grId, null);
});
```

- [ ] **Step 3: Run frontend tests and verify failure**

Run:

```powershell
node --test tests/web_table_actions.test.mjs tests/web_sc_detail_state.test.mjs
```

Expected: exports are missing and column order is not updated.

- [ ] **Step 4: Add detail route state**

In `sc_gr_app/web/components/state.js`, add:

```javascript
export const state = {
  currentView: "sc",
  user: null,
  userError: null,
  globalSearch: "",
  scDetail: {
    scId: null,
    poId: null,
    grId: null,
    record: null,
    loading: false,
    error: null,
  },
  views: {
    sc: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    vendor: { rows: [], loading: false, error: null, sort: "vendor_name", direction: "asc", filters: {} },
    po: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    gr: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
    logs: { rows: [], loading: false, error: null, sort: "created_at", direction: "desc", filters: {} },
  },
};

export function setScDetailTarget(scId, { poId = null, grId = null } = {}) {
  state.scDetail.scId = scId;
  state.scDetail.poId = poId;
  state.scDetail.grId = grId;
}

export function clearScDetailTarget() {
  state.scDetail.scId = null;
  state.scDetail.poId = null;
  state.scDetail.grId = null;
  state.scDetail.record = null;
  state.scDetail.loading = false;
  state.scDetail.error = null;
}
```

- [ ] **Step 5: Export column definitions**

In `sc_gr_app/web/components/views.js`, add:

```javascript
export function getColumnsForView(viewKey) {
  return VIEW_DEFINITIONS[viewKey]?.columns ?? [];
}
```

Reorder SC/PO/GR columns so `status` is first and add an actions column last:

```javascript
{ key: "status", label: "Status", sortKey: "status", width: "11%", render: statusBadge },
{ key: "sc_no", label: "SC No", sortKey: "sc_no", width: "13%" },
{ key: "requester_name", label: "Requester", sortKey: "requester_name", width: "13%" },
{ key: "request_type", label: "Type", sortKey: "request_type", width: "12%" },
{ key: "cost_center", label: "Cost Center", sortKey: "cost_center", width: "11%" },
{ key: "sc_amount", label: "SC Amount", sortKey: "sc_amount", width: "13%", className: "amount", render: (value) => money(value) },
{ key: "created_at", label: "Created", sortKey: "created_at", width: "12%", render: (value) => date(value) },
{ key: "description", label: "Description", sortKey: null },
{ key: "actions", label: "Actions", sortKey: null, width: "86px", className: "actions", render: actionButtons },
```

- [ ] **Step 6: Add action button rendering**

In `views.js`:

```javascript
function actionButtons(value, row) {
  return `
    <button type="button" class="icon-button row-action" data-action="open-detail" title="Open SC detail">
      ↗
    </button>
  `;
}
```

- [ ] **Step 7: Update table event handling**

In `tables.js`, when action buttons are clicked, prevent the row handler from also firing:

```javascript
container.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", (event) => {
    event.stopPropagation();
    const rowElement = button.closest("tr");
    const row = rows[Number(rowElement.dataset.rowIndex)];
    options.onAction?.(button.dataset.action, row);
  });
});
```

- [ ] **Step 8: Route actions to SC Detail**

In `app.js`, add `onAction` callback to `renderView`:

```javascript
onAction: async (action, row) => {
  if (action !== "open-detail") {
    return;
  }
  if (state.currentView === "sc") {
    await routeToScDetail(row.sc_id);
  } else if (state.currentView === "po") {
    await routeToScDetail(row.sc_id, { poId: row.po_id });
  } else if (state.currentView === "gr") {
    await routeToScDetail(row.sc_id, { grId: row.gr_id });
  }
},
```

Add:

```javascript
async function routeToScDetail(scId, target = {}) {
  setScDetailTarget(scId, target);
  await routeTo("sc-detail");
}
```

Update `getViewTitle` and `renderView` to recognize `sc-detail`.

- [ ] **Step 9: Run frontend tests**

Run:

```powershell
node --test tests/web_table_actions.test.mjs tests/web_sc_detail_state.test.mjs tests/web_auth_state.test.mjs
```

Expected: frontend tests pass.

- [ ] **Step 10: Run full tests**

Run:

```powershell
uv run pytest
node --test tests/web_table_actions.test.mjs tests/web_sc_detail_state.test.mjs tests/web_auth_state.test.mjs
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```powershell
git add sc_gr_app/web/components/state.js sc_gr_app/web/components/tables.js sc_gr_app/web/components/views.js sc_gr_app/web/app.js tests/web_table_actions.test.mjs tests/web_sc_detail_state.test.mjs
git commit -m "feat(web): route list actions to SC detail"
```

## Task 7: SC New Form And SC Detail UI

**Files:**
- Create: `sc_gr_app/web/components/forms.js`
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/styles.css`
- Test: `tests/web_sc_detail_state.test.mjs`

- [ ] **Step 1: Add failing form payload tests**

Append to `tests/web_sc_detail_state.test.mjs`:

```javascript
import { collectFormData } from "../sc_gr_app/web/components/forms.js";

test("collectFormData omits empty optional values and keeps numeric strings", () => {
  const controls = [
    { name: "sc_id", value: "SC1" },
    { name: "request_type", value: "service" },
    { name: "cost_center", value: "1001" },
    { name: "description", value: "" },
  ];

  assert.deepEqual(collectFormData(controls), {
    sc_id: "SC1",
    request_type: "service",
    cost_center: "1001",
  });
});
```

- [ ] **Step 2: Run frontend tests and verify failure**

Run:

```powershell
node --test tests/web_sc_detail_state.test.mjs
```

Expected: missing `forms.js`.

- [ ] **Step 3: Create form helper**

Create `sc_gr_app/web/components/forms.js`:

```javascript
export function collectFormData(controls) {
  const data = {};
  for (const control of controls) {
    const name = control.name;
    if (!name) {
      continue;
    }
    const value = typeof control.value === "string" ? control.value.trim() : control.value;
    if (value === "" || value === null || value === undefined) {
      continue;
    }
    data[name] = value;
  }
  return data;
}

export function field(name, label, value = "", type = "text") {
  return `
    <label class="form-field">
      <span>${label}</span>
      <input name="${name}" type="${type}" value="${value ?? ""}">
    </label>
  `;
}
```

- [ ] **Step 4: Add New SC rendering**

In `views.js`, add a `renderNewSc` function that renders:

- requester ID hidden or readonly from `state.user.user_id`.
- SC fields: `sc_id`, `sc_no`, `request_type`, `cost_center`, `sc_amount`, `service_period_start`, `service_period_end`, `description`.
- Buttons: `Save Draft`, `Submit`, `Cancel`.

Button handlers call callbacks:

```javascript
callbacks.onCreateSc("draft", data)
callbacks.onCreateSc("submit", data)
```

- [ ] **Step 5: Add SC Detail rendering**

In `views.js`, add `renderScDetail(regions, callbacks)`:

- If loading, render loading panel.
- If error, render error panel.
- If no record, call `get_sc_detail`.
- Render sections:
  - `.detail-page-header`
  - `.detail-section.sc-section`
  - `.detail-section.po-section`
  - `.detail-section.gr-section`
  - `.detail-section.audit-section`

Use `detail.permissions` to show/hide buttons.

- [ ] **Step 6: Wire frontend bridge actions**

In `app.js`, add handlers:

```javascript
async function createSc(mode, data) {
  if (mode === "draft") {
    const created = await callApi("create_sc_draft", { data });
    await routeToScDetail(created.sc_id);
    return;
  }
  const created = await callApi("create_sc_draft", { data });
  const submitted = await callApi("submit_sc", { sc_id: created.sc_id, data });
  await routeToScDetail(submitted.sc_id);
}
```

Add detail action handlers for SC actions:

```javascript
await callApi("submit_sc", { sc_id, data });
await callApi("update_sc", { sc_id, data });
await callApi("approve_sc", { sc_id });
await callApi("deny_sc", { sc_id });
await callApi("close_sc", { sc_id });
```

- [ ] **Step 7: Add styles**

In `styles.css`, add:

```css
.detail-page-header,
.detail-section,
.form-grid,
.section-toolbar {
  min-width: 0;
}

.detail-page-header {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 12px;
  padding: 14px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--surface);
}

.detail-section {
  display: grid;
  gap: 12px;
  padding: 14px;
  border-top: 1px solid var(--line);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(180px, 1fr));
  gap: 10px;
}

.form-field {
  display: grid;
  gap: 5px;
}

.form-field span {
  color: var(--muted);
  font-size: 12px;
  font-weight: 700;
}

.actions {
  text-align: right;
}
```

- [ ] **Step 8: Run frontend tests**

Run:

```powershell
node --test tests/web_sc_detail_state.test.mjs tests/web_table_actions.test.mjs tests/web_auth_state.test.mjs
```

Expected: frontend tests pass.

- [ ] **Step 9: Run app smoke check**

Run:

```powershell
uv run python -m sc_gr_app.main
```

Manual smoke:

- SC list shows New SC.
- Status is first column.
- Actions is last column.
- New SC form opens.
- SC detail opens from an SC row.

Close the window after smoke check.

- [ ] **Step 10: Run full automated tests**

Run:

```powershell
uv run pytest
node --test tests/web_sc_detail_state.test.mjs tests/web_table_actions.test.mjs tests/web_auth_state.test.mjs
```

Expected: all tests pass.

- [ ] **Step 11: Commit**

```powershell
git add sc_gr_app/web/components/forms.js sc_gr_app/web/components/views.js sc_gr_app/web/app.js sc_gr_app/web/styles.css tests/web_sc_detail_state.test.mjs
git commit -m "feat(web): add SC creation and detail page"
```

## Task 8: PO And GR Forms Inside SC Detail

**Files:**
- Modify: `sc_gr_app/web/components/views.js`
- Modify: `sc_gr_app/web/app.js`
- Modify: `sc_gr_app/web/styles.css`
- Test: `tests/web_sc_detail_state.test.mjs`

- [ ] **Step 1: Add failing action metadata test**

Append to `tests/web_sc_detail_state.test.mjs`:

```javascript
import { visibleDetailActions } from "../sc_gr_app/web/components/views.js";

test("visibleDetailActions follows permission metadata", () => {
  const actions = visibleDetailActions({
    permissions: {
      can_manage_po: true,
      can_manage_gr: true,
      can_approve_sc: false,
      can_close_sc: true,
    },
  });

  assert(actions.includes("add-po"));
  assert(actions.includes("add-gr"));
  assert(actions.includes("close-sc"));
  assert(!actions.includes("approve-sc"));
});
```

- [ ] **Step 2: Run frontend test and verify failure**

Run: `node --test tests/web_sc_detail_state.test.mjs`

Expected: `visibleDetailActions` is missing.

- [ ] **Step 3: Export action helper**

In `views.js`, add:

```javascript
export function visibleDetailActions(detail) {
  const permissions = detail?.permissions ?? {};
  const actions = [];
  if (permissions.can_submit_sc) actions.push("submit-sc");
  if (permissions.can_edit_sc) actions.push("edit-sc");
  if (permissions.can_approve_sc) actions.push("approve-sc");
  if (permissions.can_deny_sc) actions.push("deny-sc");
  if (permissions.can_close_sc) actions.push("close-sc");
  if (permissions.can_manage_po) actions.push("add-po");
  if (permissions.can_manage_gr) actions.push("add-gr");
  return actions;
}
```

- [ ] **Step 4: Add PO forms in detail**

In `renderScDetail`, add:

- `Add PO` button when `can_manage_po`.
- `Edit` button on each PO row when `can_manage_po`.
- `Approve` button when PO status is `po_pending`.
- `Finish` button when PO status is `po_approved`.

Form fields:

- `po_id`
- `vendor_id`
- `po_no`
- `po_amount`
- `contract_from`
- `contract_to`
- `contract_no`
- `payment_frequency`

- [ ] **Step 5: Add GR forms in detail**

In `renderScDetail`, add:

- `Add GR` button when `can_manage_gr`.
- `Edit` button on each GR row when `can_manage_gr`.
- `Approve` button when GR status is `pending`.
- `Cancel` button when GR status is `pending`.

Form fields:

- `gr_id`
- `po_id`
- `requester_id`
- `estimated_amount`
- `con_value`
- `remark`

- [ ] **Step 6: Wire app handlers**

In `app.js`, add handlers:

```javascript
async function savePo(mode, payload) {
  if (mode === "create") {
    await callApi("create_po", { data: payload });
  } else {
    await callApi("update_po", { po_id: payload.po_id, data: payload });
  }
  await refreshScDetail();
}

async function saveGr(mode, payload) {
  if (mode === "create") {
    await callApi("create_gr", { data: payload });
  } else {
    await callApi("update_gr", { gr_id: payload.gr_id, data: payload });
  }
  await refreshScDetail();
}
```

Add status handlers:

```javascript
await callApi("approve_po", { po_id });
await callApi("finish_po", { po_id });
await callApi("approve_gr", { gr_id, con_value });
await callApi("cancel_gr", { gr_id });
```

Use `window.confirm` before `finish_po` and `cancel_gr`.

- [ ] **Step 7: Run frontend tests**

Run:

```powershell
node --test tests/web_sc_detail_state.test.mjs tests/web_table_actions.test.mjs tests/web_auth_state.test.mjs
```

Expected: frontend tests pass.

- [ ] **Step 8: Run full tests**

Run:

```powershell
uv run pytest
node --test tests/web_sc_detail_state.test.mjs tests/web_table_actions.test.mjs tests/web_auth_state.test.mjs
```

Expected: all tests pass.

- [ ] **Step 9: Manual smoke**

Run: `uv run python -m sc_gr_app.main`

Smoke:

- Open approved SC detail.
- Admin action buttons appear.
- Add PO form opens.
- Add GR form opens.
- PO/GR list actions remain query-only outside detail.

- [ ] **Step 10: Commit**

```powershell
git add sc_gr_app/web/components/views.js sc_gr_app/web/app.js sc_gr_app/web/styles.css tests/web_sc_detail_state.test.mjs
git commit -m "feat(web): manage PO and GR in SC detail"
```

## Task 9: Fixture Refresh And Final Acceptance

**Files:**
- Modify only if needed: local `data/sc_gr.sqlite3` is not tracked.
- Test: existing test suites.

- [ ] **Step 1: Run full verification**

Run:

```powershell
uv run pytest
node --test tests/web_auth_state.test.mjs tests/web_table_actions.test.mjs tests/web_sc_detail_state.test.mjs
```

Expected:

- Python tests pass.
- Node frontend tests pass.

- [ ] **Step 2: Start app**

Run:

```powershell
uv run python -m sc_gr_app.main
```

Expected:

- App launches.
- System shows authorized current user.

- [ ] **Step 3: Manual acceptance**

Use the local SQLite DB and verify:

- Requester creates a draft SC and sees it.
- Admin does not see that draft SC.
- Another requester does not see that draft SC.
- Requester submits draft without `sc_no`; SC becomes pending.
- Requester cannot edit the pending SC.
- Admin sees the pending SC.
- Admin cannot approve pending SC until `sc_no` is filled.
- Admin fills `sc_no` and approves the SC.
- Admin creates and edits PO records in SC Detail.
- Admin approves and finishes a PO.
- Admin creates and edits GR records in SC Detail.
- Admin approves and cancels GR records.
- PO and GR list actions open the correct SC Detail and focus the target record.
- The detail workflow no longer covers status columns in list pages.

- [ ] **Step 4: Check git state**

Run:

```powershell
git status --short --branch
```

Expected: clean worktree after all task commits.

- [ ] **Step 5: Commit any acceptance docs if created**

If manual acceptance notes were added as a tracked document:

```powershell
git add <acceptance-note-path>
git commit -m "docs: record SC detail acceptance notes"
```

If no tracked file was created, do not commit.

## Self-Review Notes

- Spec coverage: migration, SC draft, SC detail, visibility, PO/GR admin workflows, bridge APIs, frontend list/detail flows, and manual acceptance are covered.
- No intentional reopen/rollback behavior is included.
- Vendor edit/create remains out of scope.
- Shared-drive deployment remains out of scope.
- Every task has a focused test-first step and a verification command.
