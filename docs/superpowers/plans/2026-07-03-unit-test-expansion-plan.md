# Unit Test Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add ~100 unit tests across 2 new test files and 3 existing file patches, following the project's real-SQLite-no-mock pattern.

**Architecture:** Each test class is a group of related operations on the same service. Tests use the `app_config` fixture (tmp_path SQLite), seed users via `seed_users()`, create prerequisite data through service calls, then assert return values or `pytest.raises` for error paths.

**Tech Stack:** pytest, SQLite (via tmp_path), sc_gr_app service functions

---

### Task 1: Add `seeded_config` fixture to conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Read current conftest.py**

- [ ] **Step 2: Add `seeded_config` fixture**

```python
import pytest
from pathlib import Path
from sc_gr_app.config import AppConfig


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        db_path=tmp_path / "test.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )


@pytest.fixture()
def seeded_config(app_config: AppConfig) -> AppConfig:
    """Migrate + seed users, return config ready for tests."""
    from sc_gr_app.db.migrations import migrate
    from sc_gr_app.services.user_service import seed_users

    migrate(app_config)
    seed_users(app_config)
    return app_config
```

- [ ] **Step 3: Verify existing tests still pass with new fixture**

Run: `pytest tests/ -x --tb=short -q`
Expected: all 398 tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add seeded_config fixture to conftest"
```

---

### Task 2: Create test_sc_service.py — TestScCreate + TestScSubmit

**Files:**
- Create: `tests/test_sc_service.py`

- [ ] **Step 1: Write the test file with TestScCreate**

```python
"""Unit tests for sc_service CRUD operations."""
import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.services.sc_service import (
    add_sc_vendor,
    approve_sc,
    confirm_sc,
    create_sc,
    create_sc_draft,
    deny_sc,
    delete_sc,
    finish_sc,
    get_sc_detail,
    recall_sc,
    remove_sc_vendor,
    submit_sc,
    transfer_sc,
    update_sc,
)
from sc_gr_app.services.user_service import seed_users
from sc_gr_app.services.vendor_service import create_vendor


# -- helpers --

ADMIN = {"user_id": "A1", "role": "admin", "machine_id": "M1"}
REQUESTER = {"user_id": "U1", "role": "requester", "machine_id": "M2"}


def _resolve_users(app_config):
    """Return (admin, requester) dicts from DB after seed_users."""
    with connect(app_config) as conn:
        admin = dict(conn.execute(
            "select * from users where role = 'admin' limit 1"
        ).fetchone())
        requester = dict(conn.execute(
            "select * from users where role = 'requester' limit 1"
        ).fetchone())
    return admin, requester


class TestScCreate:
    def test_create_sc_rejects_missing_required_fields(self, seeded_config):
        """create_sc raises ValidationError when required fields are missing."""
        admin, _ = _resolve_users(seeded_config)
        with pytest.raises(ValidationError, match="requester_id is required"):
            create_sc(seeded_config, admin, {})

    def test_create_sc_rejects_invalid_request_type(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        with pytest.raises(ValidationError, match="request_type is invalid"):
            create_sc(seeded_config, admin, {
                "requester_id": requester["user_id"],
                "request_type": "invalid_type",
                "cost_center": 1000,
                "sc_amount": 50000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            })

    def test_create_sc_rejects_invalid_currency(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        with pytest.raises(ValidationError, match="currency must be one of"):
            create_sc(seeded_config, admin, {
                "requester_id": requester["user_id"],
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": 50000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
                "currency": "GBP",
            })

    def test_create_sc_rejects_non_positive_amount(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        with pytest.raises(ValidationError, match="sc_amount must be positive"):
            create_sc(seeded_config, admin, {
                "requester_id": requester["user_id"],
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": "0",
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            })

    def test_create_sc_normal_mode_creates_pending(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-001",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        assert sc["status"] == "pending"
        assert sc["sc_no"] == "SC-001"

    def test_create_sc_backfill_mode_requires_admin(self, seeded_config):
        _, requester = _resolve_users(seeded_config)
        with pytest.raises(PermissionDenied):
            create_sc(seeded_config, requester, {
                "requester_id": requester["user_id"],
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": 50000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            }, operation_mode="backfill")

    def test_create_sc_backfill_allows_approved_status(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "status": "approved",
        }, operation_mode="backfill")
        assert sc["status"] == "approved"

    def test_create_sc_fc_top_level(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FC",
            "requester_id": requester["user_id"],
            "request_type": "FC",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        assert sc["request_type"] == "FC"
        assert sc["status"] == "pending"


class TestScCreateDraft:
    def test_create_draft_only_needs_requester_id(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        assert sc["status"] == "draft"

    def test_draft_requester_cannot_create_for_other_user(self, seeded_config):
        _, requester = _resolve_users(seeded_config)
        with pytest.raises(PermissionDenied, match="Requester can only create their own draft SC"):
            create_sc_draft(seeded_config, requester, {
                "requester_id": "someone_else",
            })

    def test_draft_admin_can_create_for_any_user(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        assert sc["requester_id"] == requester["user_id"]

    def test_draft_stores_optional_fields(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
            "sc_no": "SC-DRAFT-001",
            "description": "test draft",
            "currency": "EUR",
        })
        assert sc["sc_no"] == "SC-DRAFT-001"
        assert sc["description"] == "test draft"
        assert sc["currency"] == "EUR"


class TestScSubmit:
    def test_submit_draft_to_manager_confirm(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        result = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-SUB-001",
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        assert result["status"] == "manager_confirm"

    def test_submit_denied_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DENY",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = deny_sc(seeded_config, admin, sc["sc_id"])
        result = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-RESUB",
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        assert result["status"] == "manager_confirm"

    def test_submit_rejects_non_draft_non_denied(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-APP",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(ConflictError, match="SC must be draft or denied to submit"):
            submit_sc(seeded_config, admin, sc["sc_id"], {
                "sc_no": "SC-RESUB",
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": 50000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            })

    def test_submit_rejects_missing_business_fields(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ValidationError, match="is required"):
            submit_sc(seeded_config, admin, sc["sc_id"], {
                "sc_no": "SC-BAD",
            })

    def test_submit_non_owner_requester_rejected(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        other = {"user_id": "U2", "role": "requester", "machine_id": "M3"}
        with pytest.raises(PermissionDenied, match="Only the draft owner"):
            submit_sc(seeded_config, other, sc["sc_id"], {
                "sc_no": "SC-SUB",
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": 50000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            })
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_sc_service.py -v -x`
Expected: 13 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_sc_service.py
git commit -m "test: add TestScCreate, TestScCreateDraft, TestScSubmit"
```

---

### Task 3: Create test_sc_service.py — TestScConfirm + TestScApprove + TestScUpdate

**Files:**
- Modify: `tests/test_sc_service.py` (append)

- [ ] **Step 1: Append test classes**

```python
class TestScConfirm:
    def test_confirm_manager_confirm_to_pending(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-CONF",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = confirm_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "pending"

    def test_confirm_rejects_non_manager_confirm(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ConflictError, match="SC must be in manager_confirm status"):
            confirm_sc(seeded_config, admin, sc["sc_id"])

    def test_confirm_requires_admin(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-NOAD",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(PermissionDenied):
            confirm_sc(seeded_config, requester, sc["sc_id"])


class TestScApprove:
    def test_approve_pending_to_approved(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-APPR",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        result = approve_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "approved"

    def test_approve_rejects_draft_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ConflictError, match="SC must be pending"):
            approve_sc(seeded_config, admin, sc["sc_id"])

    def test_approve_rejects_manager_confirm_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-MC",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(ConflictError, match="SC must be pending"):
            approve_sc(seeded_config, admin, sc["sc_id"])

    def test_approve_requires_admin(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-NOAD2",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        with pytest.raises(PermissionDenied):
            approve_sc(seeded_config, requester, sc["sc_id"])


class TestScUpdate:
    def test_update_sc_field(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        result = update_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-UPDATED",
            "description": "updated description",
        })
        assert result["sc_no"] == "SC-UPDATED"
        assert result["description"] == "updated description"

    def test_update_rejects_no_fields(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ValidationError, match="No SC fields to update"):
            update_sc(seeded_config, admin, sc["sc_id"], {})

    def test_update_rejects_finished_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FIN",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        sc = finish_sc(seeded_config, admin, sc["sc_id"])
        with pytest.raises(PermissionDenied, match="Cannot modify"):
            update_sc(seeded_config, admin, sc["sc_id"], {"sc_no": "SC-BAD"})

    def test_update_amount_cannot_go_below_po_allocation(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-PO-AMT",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        # Create vendor + PO that allocates 40000 of the SC
        from sc_gr_app.services.po_service import create_po
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Test Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 40000,
        })
        with pytest.raises(ConflictError, match="SC amount cannot be below allocated PO amount"):
            update_sc(seeded_config, admin, sc["sc_id"], {"sc_amount": 30000})
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_sc_service.py -v -x`
Expected: all tests in file PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_sc_service.py
git commit -m "test: add TestScConfirm, TestScApprove, TestScUpdate"
```

---

### Task 4: Create test_sc_service.py — TestScDeny + TestScFinish + TestScRecall + TestScDelete

**Files:**
- Modify: `tests/test_sc_service.py` (append)

- [ ] **Step 1: Append test classes**

```python
class TestScDeny:
    def test_deny_pending_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DENY",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = deny_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "denied"

    def test_deny_manager_confirm_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DENY2",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = deny_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "denied"

    def test_deny_rejects_draft_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ConflictError, match="SC must be pending or manager_confirm"):
            deny_sc(seeded_config, admin, sc["sc_id"])

    def test_deny_requires_admin(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DENY3",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(PermissionDenied):
            deny_sc(seeded_config, requester, sc["sc_id"])


class TestScFinish:
    def test_finish_approved_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FINISH",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        result = finish_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "finished"

    def test_finish_rejects_non_approved(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ConflictError, match="SC must be approved"):
            finish_sc(seeded_config, admin, sc["sc_id"])

    def test_finish_blocked_by_unfinished_po(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        from sc_gr_app.services.po_service import create_po
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-WPO",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Vendor X",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 30000,
        })
        with pytest.raises(ConflictError, match="PO\\(s\\) not finished"):
            finish_sc(seeded_config, admin, sc["sc_id"])


class TestScRecall:
    def test_recall_finished_to_approved(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-RECALL",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        sc = finish_sc(seeded_config, admin, sc["sc_id"])
        result = recall_sc(seeded_config, admin, sc["sc_id"])
        assert result["status"] == "approved"

    def test_recall_rejects_non_finished(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(ConflictError, match="SC must be finished"):
            recall_sc(seeded_config, admin, sc["sc_id"])

    def test_recall_requires_admin(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-REC2",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        sc = finish_sc(seeded_config, admin, sc["sc_id"])
        with pytest.raises(PermissionDenied):
            recall_sc(seeded_config, requester, sc["sc_id"])


class TestScDelete:
    def test_delete_draft_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        result = delete_sc(seeded_config, admin, sc["sc_id"])
        assert result is True

    def test_delete_rejects_non_draft(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DEL",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(ConflictError, match="Only draft SCs can be deleted"):
            delete_sc(seeded_config, admin, sc["sc_id"])

    def test_delete_requires_admin(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        with pytest.raises(PermissionDenied):
            delete_sc(seeded_config, requester, sc["sc_id"])
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_sc_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_sc_service.py
git commit -m "test: add TestScDeny, TestScFinish, TestScRecall, TestScDelete"
```

---

### Task 5: Create test_sc_service.py — TestScTransfer + TestScVendors + TestScDetail + TestScCallOff

**Files:**
- Modify: `tests/test_sc_service.py` (append)

- [ ] **Step 1: Append test classes**

```python
class TestScTransfer:
    def test_transfer_sc_ownership(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-XFER",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = transfer_sc(seeded_config, admin, sc["sc_id"], admin["user_id"])
        assert result["requester_id"] == admin["user_id"]

    def test_transfer_to_same_owner_is_noop(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-SAME",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = transfer_sc(seeded_config, admin, sc["sc_id"], requester["user_id"])
        assert result == sc

    def test_transfer_rejects_nonexistent_target(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-NOEX",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        with pytest.raises(ValidationError, match="目标用户不存在"):
            transfer_sc(seeded_config, admin, sc["sc_id"], "NONEXISTENT")


class TestScVendors:
    def test_add_vendor_to_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Vendor A",
            "service_scope": "General Service",
        })
        vendors = add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        assert len(vendors) == 1
        assert vendors[0]["vendor_id"] == v["vendor_id"]

    def test_add_duplicate_vendor_rejected(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Vendor B",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        with pytest.raises(ConflictError, match="already linked"):
            add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])

    def test_remove_vendor_from_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Vendor C",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        vendors = remove_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        assert len(vendors) == 0

    def test_remove_unlinked_vendor_rejected(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Vendor D",
            "service_scope": "General Service",
        })
        with pytest.raises(ConflictError, match="not linked"):
            remove_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])


class TestScDetail:
    def test_get_sc_detail(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-DETAIL",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        detail = get_sc_detail(seeded_config, admin, sc["sc_id"])
        assert detail["sc"]["sc_id"] == sc["sc_id"]
        assert "vendors" in detail

    def test_detail_includes_calloff_parent_context(self, seeded_config):
        """Call-off SC detail includes parent PO(FC) info."""
        admin, requester = _resolve_users(seeded_config)
        # Create FC chain
        sc_fc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FC",
            "requester_id": requester["user_id"],
            "request_type": "FC",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc_fc = approve_sc(seeded_config, admin, sc_fc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "FC Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc_fc["sc_id"], v["vendor_id"])
        from sc_gr_app.services.po_service import create_po
        po_fc = create_po(seeded_config, admin, {
            "sc_id": sc_fc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        co = create_sc(seeded_config, admin, {
            "sc_no": "SC-CO",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 30000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-06-30",
            "calloff_po_id": po_fc["po_id"],
        })
        detail = get_sc_detail(seeded_config, admin, co["sc_id"])
        assert detail["sc"]["calloff_po_id"] == po_fc["po_id"]


class TestScCallOff:
    def test_calloff_validated_in_create_sc(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc_fc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FC-001",
            "requester_id": requester["user_id"],
            "request_type": "FC",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc_fc = approve_sc(seeded_config, admin, sc_fc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "V FC",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc_fc["sc_id"], v["vendor_id"])
        from sc_gr_app.services.po_service import create_po
        po_fc = create_po(seeded_config, admin, {
            "sc_id": sc_fc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        # Call-off under FC PO should work
        sc = create_sc(seeded_config, admin, {
            "sc_no": "SC-CO-001",
            "requester_id": requester["user_id"],
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 30000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "calloff_po_id": po_fc["po_id"],
        })
        assert sc["calloff_po_id"] == po_fc["po_id"]

    def test_calloff_exceeding_po_fc_budget_rejected(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc_fc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FC-002",
            "requester_id": requester["user_id"],
            "request_type": "FC",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc_fc = approve_sc(seeded_config, admin, sc_fc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "V FC2",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc_fc["sc_id"], v["vendor_id"])
        from sc_gr_app.services.po_service import create_po
        po_fc = create_po(seeded_config, admin, {
            "sc_id": sc_fc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        with pytest.raises(ConflictError, match="Call-off SC total would exceed"):
            create_sc(seeded_config, admin, {
                "sc_no": "SC-CO-BIG",
                "requester_id": requester["user_id"],
                "request_type": "material",
                "cost_center": 1000,
                "sc_amount": 60000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
                "calloff_po_id": po_fc["po_id"],
            })
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_sc_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_sc_service.py
git commit -m "test: add TestScTransfer, TestScVendors, TestScDetail, TestScCallOff"
```

---

### Task 6: Create test_gr_service.py — TestGrCreate + TestGrSubmit

**Files:**
- Create: `tests/test_gr_service.py`

- [ ] **Step 1: Write the test file**

```python
"""Unit tests for gr_service CRUD operations."""
import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.services.gr_service import (
    approve_gr,
    confirm_gr,
    create_gr,
    delete_gr,
    deny_gr,
    finish_gr,
    recall_gr,
    submit_gr,
    update_gr,
)
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.sc_service import (
    add_sc_vendor,
    approve_sc,
    confirm_sc,
    create_sc,
    create_sc_draft,
    submit_sc,
)
from sc_gr_app.services.user_service import seed_users
from sc_gr_app.services.vendor_service import create_vendor


def _resolve_users(app_config):
    with connect(app_config) as conn:
        admin = dict(conn.execute(
            "select * from users where role = 'admin' limit 1"
        ).fetchone())
        requester = dict(conn.execute(
            "select * from users where role = 'requester' limit 1"
        ).fetchone())
    return admin, requester


def _setup_approved_sc_with_active_po(app_config):
    """Create SC(approved) + vendor + PO(active). Returns (admin, requester, sc, po)."""
    admin, requester = _resolve_users(app_config)
    sc = create_sc(app_config, admin, {
        "sc_no": "SC-TEST",
        "requester_id": requester["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc = confirm_sc(app_config, admin, sc["sc_id"])
    sc = approve_sc(app_config, admin, sc["sc_id"])
    v = create_vendor(app_config, admin, {
        "vendor_name": "Test Vendor",
        "service_scope": "General Service",
    })
    add_sc_vendor(app_config, admin, sc["sc_id"], v["vendor_id"])
    po = create_po(app_config, admin, {
        "sc_id": sc["sc_id"],
        "vendor_id": v["vendor_id"],
        "po_amount": 50000,
    })
    return admin, requester, sc, po


class TestGrCreate:
    def test_create_gr_rejects_missing_required_fields(self, seeded_config):
        admin, _ = _resolve_users(seeded_config)
        with pytest.raises(ValidationError, match="po_id is required"):
            create_gr(seeded_config, admin, {})

    def test_create_gr_rejects_nonexistent_po(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        with pytest.raises(NotFound, match="PO not found"):
            create_gr(seeded_config, admin, {
                "po_id": "PO-FAKE",
                "requester_id": requester["user_id"],
                "estimated_amount": 1000,
            })

    def test_create_gr_under_active_po_creates_pending(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        assert gr["status"] == "pending"
        assert gr["po_id"] == po["po_id"]

    def test_create_gr_rejects_fc_po(self, seeded_config):
        """Cannot create GR directly under an FC PO."""
        admin, requester = _resolve_users(seeded_config)
        sc_fc = create_sc(seeded_config, admin, {
            "sc_no": "SC-FC",
            "requester_id": requester["user_id"],
            "request_type": "FC",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc_fc = approve_sc(seeded_config, admin, sc_fc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "FC Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc_fc["sc_id"], v["vendor_id"])
        po_fc = create_po(seeded_config, admin, {
            "sc_id": sc_fc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        with pytest.raises(ConflictError, match="Cannot create GR under an FC PO"):
            create_gr(seeded_config, admin, {
                "po_id": po_fc["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 10000,
            })

    def test_create_gr_rejects_non_positive_amount(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        with pytest.raises(ValidationError, match="estimated_amount must be positive"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": "0",
            })

    def test_create_gr_non_owner_requester_rejected(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        other = {"user_id": "U2", "role": "requester", "machine_id": "M3"}
        with pytest.raises(PermissionDenied, match="Only the SC owner or admin"):
            create_gr(seeded_config, other, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 10000,
            })

    def test_create_gr_admin_bypasses_owner_check(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        assert gr["status"] == "pending"


class TestGrSubmit:
    def test_submit_draft_gr_to_manager_confirm(self, seeded_config):
        """Submit a draft GR (created under active PO) transitions to manager_confirm."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        assert gr["status"] == "draft"
        result = submit_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "manager_confirm"

    def test_submit_gr_rejects_non_draft(self, seeded_config):
        """GR created without explicit status becomes pending (under active PO),
        cannot be submitted again."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        # Auto-derived as pending under active PO
        assert gr["status"] == "pending"
        with pytest.raises(ConflictError, match="GR must be draft to submit"):
            submit_gr(seeded_config, admin, gr["gr_id"])

    def test_submit_gr_requires_active_po(self, seeded_config):
        """GR under draft PO cannot be submitted (PO must be active first)."""
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {"requester_id": requester["user_id"]})
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "V Draft",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="PO must be active"):
            submit_gr(seeded_config, admin, gr["gr_id"])
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_gr_service.py -v -x`
Expected: 10 PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gr_service.py
git commit -m "test: add TestGrCreate, TestGrSubmit"
```

---

### Task 7: Create test_gr_service.py — TestGrConfirm + TestGrApprove

**Files:**
- Modify: `tests/test_gr_service.py` (append)

- [ ] **Step 1: Append test classes**

```python
class TestGrConfirm:
    def test_confirm_manager_confirm_to_pending(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = confirm_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "pending"

    def test_confirm_rejects_non_manager_confirm(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "pending",
        })
        with pytest.raises(ConflictError, match="GR must be in manager_confirm status"):
            confirm_gr(seeded_config, admin, gr["gr_id"])

    def test_confirm_requires_admin(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(PermissionDenied):
            confirm_gr(seeded_config, requester, gr["gr_id"])


class TestGrApprove:
    def test_approve_gr_sets_con_value(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = approve_gr(seeded_config, admin, gr["gr_id"], con_value=9500)
        assert result["status"] == "approved"
        assert result["con_value"] == 9500.0

    def test_approve_gr_with_tax_calculation(self, seeded_config):
        """approve_gr computes gross_cost from tax_rate when provided."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        assert result["con_value"] == 10000.0

    def test_approve_rejects_null_con_value(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ValidationError, match="con_value is required"):
            approve_gr(seeded_config, admin, gr["gr_id"], con_value=None)

    def test_approve_rejects_non_pending_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        with pytest.raises(ConflictError, match="GR must be pending or manager_confirm"):
            approve_gr(seeded_config, admin, gr["gr_id"], con_value=5000)

    def test_approve_requires_admin(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(PermissionDenied):
            approve_gr(seeded_config, requester, gr["gr_id"], con_value=5000)
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_gr_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gr_service.py
git commit -m "test: add TestGrConfirm, TestGrApprove"
```

---

### Task 8: Create test_gr_service.py — remaining classes (TestGrUpdate, TestGrDeny, TestGrFinish, TestGrRecall, TestGrDelete, TestGrValidation)

**Files:**
- Modify: `tests/test_gr_service.py` (append)

- [ ] **Step 1: Append remaining test classes**

```python
class TestGrUpdate:
    def test_update_gr_con_value(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = update_gr(seeded_config, admin, gr["gr_id"], {
            "con_value": "8500",
        })
        assert result["con_value"] == 8500.0

    def test_update_gr_rejects_finished_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        gr = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        gr = finish_gr(seeded_config, admin, gr["gr_id"])
        with pytest.raises(ConflictError, match="Cannot update finished GR"):
            update_gr(seeded_config, admin, gr["gr_id"], {"con_value": "5000"})

    def test_update_gr_estimated_amount_recalculates_tax(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = update_gr(seeded_config, admin, gr["gr_id"], {
            "estimated_amount": "20000",
        })
        assert result["estimated_amount"] == 20000.0


class TestGrDeny:
    def test_deny_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = deny_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "denied"

    def test_deny_rejects_already_denied(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        deny_gr(seeded_config, admin, gr["gr_id"])
        with pytest.raises(ConflictError, match="GR must be pending"):
            deny_gr(seeded_config, admin, gr["gr_id"])

    def test_deny_requires_admin(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(PermissionDenied):
            deny_gr(seeded_config, requester, gr["gr_id"])


class TestGrFinish:
    def test_finish_approved_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        gr = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        result = finish_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "finished"

    def test_finish_rejects_non_approved(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="GR must be approved"):
            finish_gr(seeded_config, admin, gr["gr_id"])


class TestGrRecall:
    def test_recall_finished_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        gr = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        gr = finish_gr(seeded_config, admin, gr["gr_id"])
        result = recall_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "approved"

    def test_recall_rejects_non_finished(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="GR must be finished"):
            recall_gr(seeded_config, admin, gr["gr_id"])

    def test_recall_requires_admin(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        gr = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        gr = finish_gr(seeded_config, admin, gr["gr_id"])
        with pytest.raises(PermissionDenied):
            recall_gr(seeded_config, requester, gr["gr_id"])


class TestGrDelete:
    def test_delete_draft_gr(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        result = delete_gr(seeded_config, admin, gr["gr_id"])
        assert result is True

    def test_delete_rejects_non_draft(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="Only draft GRs can be deleted"):
            delete_gr(seeded_config, admin, gr["gr_id"])

    def test_delete_requires_admin(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        with pytest.raises(PermissionDenied):
            delete_gr(seeded_config, requester, gr["gr_id"])


class TestGrValidation:
    def test_draft_po_allows_only_draft_gr(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {"requester_id": requester["user_id"]})
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "V Draft",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": 50000,
        })
        with pytest.raises(ConflictError, match="Draft PO only allows draft GR"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 10000,
                "status": "pending",
            })

    def test_gr_creation_fails_when_sc_amount_insufficient(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        with pytest.raises(ConflictError, match="SC available amount is insufficient"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 999999,
            })

    def test_gr_creation_fails_when_po_open_amount_insufficient(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        with pytest.raises(ConflictError, match="PO open amount is insufficient"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 99999,
            })
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_gr_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_gr_service.py
git commit -m "test: add TestGrUpdate, TestGrDeny, TestGrFinish, TestGrRecall, TestGrDelete, TestGrValidation"
```

---

### Task 9: Patch test_po_service.py — add regular PO operation tests

**Files:**
- Modify: `tests/test_po_service.py` (append)

- [ ] **Step 1: Append TestPoCreate and TestPoSubmit classes**

```python
class TestPoCreate:
    def test_create_po_rejects_missing_required_fields(self, seeded_config):
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
        with pytest.raises(ValidationError, match="is required"):
            create_po(seeded_config, admin, {})


class TestPoSubmit:
    def test_submit_draft_po_to_active(self, seeded_config):
        """Submit draft PO under draft SC transitions to active."""
        from sc_gr_app.services.po_service import submit_po
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
            requester = dict(conn.execute(
                "select * from users where role = 'requester' limit 1"
            ).fetchone())

        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_id": "V-PO-SUB",
            "vendor_name": "PO Submit Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KSUB",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        assert po["status"] == "draft"

        result = submit_po(seeded_config, admin, po["po_id"])
        assert result["status"] == "active"


class TestPoFinishNonFc:
    def test_finish_active_po(self, seeded_config):
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
            requester = dict(conn.execute(
                "select * from users where role = 'requester' limit 1"
            ).fetchone())

        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-PO-FIN",
            "request_type": "material",
            "cost_center": "CC-001",
            "sc_amount": "50000",
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_id": "V-FIN",
            "vendor_name": "Finish Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KFIN",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        result = finish_po(seeded_config, admin, po["po_id"])
        assert result["status"] == "finished"


class TestPoDeleteNonFc:
    def test_delete_draft_po(self, seeded_config):
        from sc_gr_app.services.po_service import delete_po
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
            requester = dict(conn.execute(
                "select * from users where role = 'requester' limit 1"
            ).fetchone())

        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        v = create_vendor(seeded_config, admin, {
            "vendor_id": "V-DEL-PO",
            "vendor_name": "Delete PO Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KDELPO",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        result = delete_po(seeded_config, admin, po["po_id"])
        assert result is True


class TestPoRecallNonFc:
    def test_recall_finished_po(self, seeded_config):
        from sc_gr_app.services.po_service import recall_po as recall_po_fn
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
            requester = dict(conn.execute(
                "select * from users where role = 'requester' limit 1"
            ).fetchone())

        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-PO-REC",
            "request_type": "material",
            "cost_center": "CC-001",
            "sc_amount": "50000",
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_id": "V-REC-PO",
            "vendor_name": "Recall PO Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KRECPO",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        po = finish_po(seeded_config, admin, po["po_id"])
        result = recall_po_fn(seeded_config, admin, po["po_id"])
        assert result["status"] == "active"
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_po_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_po_service.py
git commit -m "test: add TestPoCreate, TestPoSubmit, TestPoFinishNonFc, TestPoDeleteNonFc, TestPoRecallNonFc"
```

---

### Task 10: Patch test_budget_service.py — add manager_confirm + draft exclusion tests

**Files:**
- Modify: `tests/test_budget_service.py` (append)

- [ ] **Step 1: Append missing edge case tests**

```python
def test_po_budget_includes_manager_confirm_grs(app_config):
    """manager_confirm GRs count towards pending totals."""
    from sc_gr_app.db.connection import connect
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount=1000)
        seed_vendor(conn)
        seed_po(conn, po_amount=500)
        seed_gr(conn, "GR1", estimated_amount=100, status="manager_confirm")
        seed_gr(conn, "GR2", estimated_amount=50, status="manager_confirm")
        conn.commit()

    budget = compute_po_budget(app_config, "PO1")
    assert budget["po_pending_total"] == 150.0
    assert budget["open_po_amount"] == 350.0  # 500 - 150


def test_draft_and_finished_grs_excluded_from_budget(app_config):
    """Draft and finished GRs should not affect budget calculations."""
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount=1000)
        seed_vendor(conn)
        seed_po(conn, po_amount=500)
        seed_gr(conn, "GR1", estimated_amount=100, status="draft")
        seed_gr(conn, "GR2", estimated_amount=200, con_value=200, status="finished")
        conn.commit()

    budget = compute_po_budget(app_config, "PO1")
    assert budget["po_pending_total"] == 0.0
    assert budget["open_po_amount"] == 500.0


def test_decimal_budget_empty_db(app_config):
    """Decimal budget variants work with empty database."""
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount=1000)
        conn.commit()

    decimal_budget = compute_sc_budget_decimal(app_config, "SC1")
    assert decimal_budget["sc_available_amount"] == 1000
    assert decimal_budget["sc_pending_total"] == 0
    assert decimal_budget["allocated_po_amount"] == 0
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_budget_service.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_budget_service.py
git commit -m "test: add manager_confirm GR, draft/finished exclusion, empty DB decimal tests"
```

---

### Task 11: Patch test_fc_calloff_flow.py — add mixed status + denied exclusion tests

**Files:**
- Modify: `tests/test_fc_calloff_flow.py` (append)

- [ ] **Step 1: Append tests**

```python
def test_mixed_calloff_statuses_budget(app_config):
    """Denied call-off SCs should not consume PO(FC) budget."""
    migrate(app_config)
    seed_users(app_config)

    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-MIX",
        "requester_id": USER["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(app_config, ADMIN, sc_fc["sc_id"])
    vendor_id = _create_vendor_and_link(app_config, sc_fc["sc_id"])
    po_fc = create_po(app_config, ADMIN, {
        "sc_id": sc_fc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 80000,
    })

    # Create approved call-off SC (30000)
    create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-APPROVED",
        "requester_id": USER["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    # Create then deny a call-off SC (40000 — should NOT consume budget)
    co_denied = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-DENIED",
        "requester_id": USER["user_id"],
        "request_type": "service",
        "cost_center": 1000,
        "sc_amount": 40000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    from sc_gr_app.services.sc_service import deny_sc as deny_sc_fn
    deny_sc_fn(app_config, ADMIN, co_denied["sc_id"])

    # Budget should only count the approved call-off
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 30000.0
    assert fc_budget["open_po_amount"] == 50000.0  # 80000 - 30000


def test_denied_calloff_releases_budget(app_config):
    """After denying a call-off SC, budget is released for new call-offs."""
    migrate(app_config)
    seed_users(app_config)

    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-REL",
        "requester_id": USER["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc_fc = approve_sc(app_config, ADMIN, sc_fc["sc_id"])
    vendor_id = _create_vendor_and_link(app_config, sc_fc["sc_id"])
    po_fc = create_po(app_config, ADMIN, {
        "sc_id": sc_fc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 80000,
    })

    co = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-REL",
        "requester_id": USER["user_id"],
        "request_type": "material",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    from sc_gr_app.services.sc_service import deny_sc as deny_sc_fn
    deny_sc_fn(app_config, ADMIN, co["sc_id"])

    # After denial, should be able to create new call-off within budget
    new_co = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-NEW",
        "requester_id": USER["user_id"],
        "request_type": "service",
        "cost_center": 1000,
        "sc_amount": 70000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    assert new_co["calloff_po_id"] == po_fc["po_id"]
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_fc_calloff_flow.py -v -x`
Expected: all tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_fc_calloff_flow.py
git commit -m "test: add mixed-status call-off and denied budget release tests"
```

---

### Task 12: Clean up — delete test_sc_service_calloff.py

**Files:**
- Delete: `tests/test_sc_service_calloff.py`

- [ ] **Step 1: Verify its tests are covered by test_sc_service.py**

Run: `pytest tests/test_sc_service.py tests/test_fc_calloff_flow.py -v -q`
Expected: all tests PASS (call-off coverage in new files)

- [ ] **Step 2: Delete the file**

```bash
rm tests/test_sc_service_calloff.py
```

- [ ] **Step 3: Run full test suite**

Run: `pytest tests/ -v -q`
Expected: all tests PASS

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: remove test_sc_service_calloff.py, absorbed into test_sc_service.py"
```

---

## Final Verification

- [ ] Run full test suite: `pytest tests/ -v`
- [ ] Confirm test count increase: `pytest tests/ --co -q | wc -l`
- [ ] Confirm no regressions: all original 398 tests still pass
