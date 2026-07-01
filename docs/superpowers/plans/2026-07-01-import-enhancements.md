# Import Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restrict SC/PO/GR imports to allowed statuses, add required-field validation, add preview step before import, and show import rules on templates.

**Architecture:** Backend gets new preview functions (validate-without-insert) and updated constants/validation in import_service.py, plus new bridge endpoints. Frontend gets a reusable ImportPreviewDialog component (generalized from VendorImportDialog) replacing inline import dialogs in the three list views. Templates get an info row and updated hints.

**Tech Stack:** Python 3.11, Vue 3 + Element Plus, xlsx library (frontend), pytest

---

### File Structure

| File | Responsibility |
|------|---------------|
| `sc_gr_app/services/import_service.py` | Status constants, field validation, preview functions, confirm import functions |
| `sc_gr_app/api/bridge.py` | Bridge endpoints: preview_*_import for each entity, updated template downloads |
| `frontend/src/components/common/ImportPreviewDialog.vue` | **New** — reusable two-step (select file → preview) dialog with checkbox selection |
| `frontend/src/views/ScListView.vue` | Replace inline import dialog with ImportPreviewDialog |
| `frontend/src/views/PoListView.vue` | Same |
| `frontend/src/views/GrListView.vue` | Same |
| `frontend/src/i18n/locales/en-US.js` | New i18n keys for import rules and preview UI |
| `frontend/src/i18n/locales/zh-CN.js` | Same (Chinese) |
| `tests/test_import_service.py` | **New** — tests for status restrictions, required fields, preview annotations |

---

### Task 1: Write backend tests for import restrictions and preview

**Files:**
- Create: `tests/test_import_service.py`

- [ ] **Step 1: Write the test file covering status restrictions, required fields, preview annotations, and confirm import**

```python
"""Tests for import_service — status restrictions, required fields, preview functions."""
import pytest
from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services import import_service
from sc_gr_app.errors import ValidationError
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _seed_user(conn, user_id="U000001", machine_id="M000001", role="requester"):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, display_name, role, is_active) VALUES (?, ?, ?, ?, 1)",
        (user_id, machine_id, f"User {user_id}", role),
    )
    conn.commit()


def _seed_sc(conn, sc_id="SC-0000001-20260701-001"):
    conn.execute(
        """INSERT OR IGNORE INTO sc_records (sc_id, sc_no, requester_id, status, sc_amount, description, asset, created_by, created_at, updated_at)
           VALUES (?, ?, 'U000001', 'approved', 100000, 'Test SC', 'N', 'U000001', ?, ?)""",
        (sc_id, f"SCNO-{sc_id}", _utc_now(), _utc_now()),
    )
    conn.commit()


def _seed_po(conn, po_id="PO-0000001-20260701-001", sc_id="SC-0000001-20260701-001"):
    conn.execute(
        """INSERT OR IGNORE INTO pos (po_id, sc_id, po_no, vendor_id, requester_id, po_amount, status, created_at, updated_at)
           VALUES (?, ?, ?, 'V000001', 'U000001', 50000, 'active', ?, ?)""",
        (po_id, sc_id, f"PONO-{po_id}", _utc_now(), _utc_now()),
    )
    conn.commit()


def _seed_vendor(conn):
    conn.execute(
        "INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_at) VALUES ('V000001', 'Test Vendor', 'IT', ?)",
        (_utc_now(),),
    )
    conn.commit()


class TestScImportStatusRestrictions:
    def test_rejects_draft_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-001", "sc_amount": "50000", "status": "draft"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("Invalid status" in e for e in preview[0]["_errors"])

    def test_rejects_pending_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-002", "sc_amount": "50000", "status": "pending"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_accepts_approved_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-003", "sc_amount": "50000", "status": "approved"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_accepts_finished_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-004", "sc_amount": "50000", "status": "finished"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is True


class TestPoImportStatusRestrictions:
    def test_rejects_draft_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_no": "PO-001", "po_amount": "50000", "status": "draft"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_accepts_active_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_no": "PO-001", "po_amount": "50000", "status": "active"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_accepts_finished_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_no": "PO-001", "po_amount": "50000", "status": "finished"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is True


class TestGrImportStatusRestrictions:
    def _seed_gr_deps(self, conn):
        _seed_user(conn)
        _seed_sc(conn)
        _seed_vendor(conn)
        _seed_po(conn)

    def test_rejects_draft_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "draft"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_rejects_pending_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "pending"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_rejects_manager_confirm_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "manager_confirm"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_accepts_approved_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_accepts_finished_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "finished"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is True


class TestRequiredFields:
    def test_sc_fails_without_sc_no(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_amount": "50000", "status": "approved"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("sc_no is required" in e for e in preview[0]["_errors"])

    def test_sc_fails_without_sc_amount(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-001", "status": "approved"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("sc_amount is required" in e for e in preview[0]["_errors"])

    def test_po_fails_without_po_no(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_amount": "50000", "status": "active"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("po_no is required" in e for e in preview[0]["_errors"])

    def test_gr_fails_without_gr_no(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "estimated_amount": "10000", "con_value": "10000",
                  "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("gr_no is required" in e for e in preview[0]["_errors"])

    def test_gr_fails_without_con_value(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("con_value is required" in e for e in preview[0]["_errors"])

    def test_gr_fails_without_delivery_from(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_to": "2026-12-31", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("delivery_from is required" in e for e in preview[0]["_errors"])

    def test_gr_fails_without_delivery_to(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("delivery_to is required" in e for e in preview[0]["_errors"])


class TestPreviewAnnotations:
    def test_preview_sc_annotates_rows(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-OK", "sc_amount": "50000", "status": "approved"},
                {"sc_no": "SC-BAD", "sc_amount": "50000", "status": "draft"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert len(preview) == 2
        for row in preview:
            assert "_errors" in row
            assert "_valid" in row
            assert isinstance(row["_errors"], list)
            assert isinstance(row["_valid"], bool)

    def test_preview_does_not_insert_into_db(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_no": "SC-OK", "sc_amount": "50000", "status": "approved"}]
        import_service.preview_sc_import(app_config, rows)
        with connect(app_config) as conn:
            count = conn.execute("SELECT COUNT(*) FROM sc_records").fetchone()[0]
        assert count == 0

    def test_preview_skips_template_meta_rows(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        rows = [{"sc_id": "[EXAMPLE]", "sc_no": "", "sc_amount": "50000", "status": "draft"}]
        preview = import_service.preview_sc_import(app_config, rows)
        assert len(preview) == 0

    def test_preview_po_annotates_rows(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_no": "PO-001", "po_amount": "50000", "status": "active"}]
        preview = import_service.preview_po_import(app_config, rows)
        assert len(preview) == 1
        assert "_errors" in preview[0]
        assert "_valid" in preview[0]

    def test_preview_gr_annotates_rows(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert len(preview) == 1
        assert "_errors" in preview[0]
        assert "_valid" in preview[0]


class TestConfirmImport:
    def test_confirm_sc_import_with_required_fields(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
        current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
        rows = [{"sc_no": "SC-CONFIRM", "sc_amount": "50000", "status": "approved"}]
        result = import_service.import_scs(app_config, current_user, rows)
        assert result["ok"] is True
        assert result["count"] == 1

    def test_confirm_po_import_with_required_fields(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
        current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
        rows = [{"sc_id": "SC-0000001-20260701-001", "po_no": "PO-CONFIRM", "po_amount": "50000", "status": "active"}]
        result = import_service.import_pos(app_config, current_user, rows)
        assert result["ok"] is True
        assert result["count"] == 1

    def test_confirm_gr_import_with_required_fields(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn)
            _seed_sc(conn)
            _seed_vendor(conn)
            _seed_po(conn)
        current_user = {"user_id": "U000001", "machine_id": "M000001", "role": "requester"}
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-CONFIRM", "estimated_amount": "10000",
                  "con_value": "10000", "delivery_from": "2026-01-01", "delivery_to": "2026-12-31", "status": "approved"}]
        result = import_service.import_grs(app_config, current_user, rows)
        assert result["ok"] is True
        assert result["count"] == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
uv run pytest tests/test_import_service.py -v
```

Expected: All tests FAIL because the new status constants, required-field validation, and preview functions don't exist yet.

- [ ] **Step 3: Commit**

```bash
git add tests/test_import_service.py
git commit -m "test: add import service tests for status restrictions, required fields, and preview"
```

---

### Task 2: Update status constants and required-field validation

**Files:**
- Modify: `sc_gr_app/services/import_service.py:10,174-201,285-306`

- [ ] **Step 1: Replace status constants and add sc_no/po_no to required fields**

In `sc_gr_app/services/import_service.py`, replace line 10:

```python
# Replace:
SC_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "finished"}

# With:
SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}
```

Replace line 174:

```python
# Replace:
PO_ALLOWED_STATUSES = {"draft", "active", "finished"}

# With:
PO_IMPORT_ALLOWED_STATUSES = {"active", "finished"}
```

Replace line 285:

```python
# Replace:
GR_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "finished"}

# With:
GR_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}
```

- [ ] **Step 2: Update references from old constant names to new names**

In `_validate_sc_rows` (line 85), replace `SC_ALLOWED_STATUSES` with `SC_IMPORT_ALLOWED_STATUSES`.

In `_validate_po_rows` (line 187), replace `PO_ALLOWED_STATUSES` with `PO_IMPORT_ALLOWED_STATUSES`.

In `_validate_gr_rows` (line 298), replace `GR_ALLOWED_STATUSES` with `GR_IMPORT_ALLOWED_STATUSES`.

- [ ] **Step 3: Add sc_no to SC required fields**

In `_validate_sc_rows` (around lines 81-82), change the required field loop:

```python
# Replace:
for field in ["sc_amount", "status"]:

# With:
for field in ["sc_no", "sc_amount", "status"]:
```

- [ ] **Step 4: Add po_no to PO required fields**

In `_validate_po_rows` (around lines 183-184), change the required field loop:

```python
# Replace:
for field in ["sc_id", "po_amount", "status"]:

# With:
for field in ["sc_id", "po_no", "po_amount", "status"]:
```

- [ ] **Step 5: Add gr_no, con_value, delivery_from, delivery_to to GR required fields**

In `_validate_gr_rows` (around lines 294-295), change the required field loop:

```python
# Replace:
for field in ["po_id", "estimated_amount", "status"]:

# With:
for field in ["po_id", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
```

- [ ] **Step 6: Run tests — status restriction and required-field tests should now pass**

```
uv run pytest tests/test_import_service.py -v -k "StatusRestrictions or RequiredFields"
```

Expected: Status restriction tests and required-field tests PASS. Preview/confirm tests may still fail (preview functions not yet added).

- [ ] **Step 7: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: restrict import statuses and add required-field validation for SC/PO/GR"
```

---

### Task 3: Add preview functions to import_service.py

**Files:**
- Modify: `sc_gr_app/services/import_service.py` (add functions after existing `_validate_gr_rows` on line 306)

- [ ] **Step 1: Add preview_sc_import function**

Insert after `_validate_gr_rows` (line 306):

```python
def preview_sc_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate SC rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "sc_id"):
                continue
            errors_list = []
            for field in ["sc_no", "sc_amount", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in SC_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("requester_id"):
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"User {row['requester_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview


def preview_po_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate PO rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "po_id"):
                continue
            errors_list = []
            for field in ["sc_id", "po_no", "po_amount", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in PO_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("sc_id"):
                exists = conn.execute(
                    "SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"SC {row['sc_id']} not found")
            if row.get("vendor_id"):
                exists = conn.execute(
                    "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"Vendor {row['vendor_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview


def preview_gr_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate GR rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "gr_id"):
                continue
            errors_list = []
            for field in ["po_id", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in GR_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("po_id"):
                exists = conn.execute(
                    "SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"PO {row['po_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview
```

- [ ] **Step 2: Run preview annotation and confirm import tests**

```
uv run pytest tests/test_import_service.py -v -k "PreviewAnnotations or ConfirmImport"
```

Expected: All remaining tests PASS.

- [ ] **Step 3: Run full test suite to check for regressions**

```
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 4: Commit**

```bash
git add sc_gr_app/services/import_service.py
git commit -m "feat: add preview functions for SC/PO/GR import validation"
```

---

### Task 4: Add bridge preview endpoints and update templates

**Files:**
- Modify: `sc_gr_app/api/bridge.py` (after line 1703 for SC, 1798 for PO, 1894 for GR — after each `download_*_template` method)

- [ ] **Step 1: Add preview_sc_import bridge method**

Insert after `download_sc_template` method (after line 1703):

```python
    def preview_sc_import(self, payload) -> dict:
        """Validate SC import rows without inserting. Returns annotated rows.
        
        Note: intentionally does NOT call _require_current_user() — preview is read-only
        validation that does not write to the database, so no auth check is needed.
        """
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_sc_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)
```

- [ ] **Step 2: Add preview_po_import bridge method**

Insert after `download_po_template` method (after line 1798):

```python
    def preview_po_import(self, payload) -> dict:
        """Validate PO import rows without inserting. Returns annotated rows."""
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_po_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)
```

- [ ] **Step 3: Add preview_gr_import bridge method**

Insert after `download_gr_template` method (after line 1894):

```python
    def preview_gr_import(self, payload) -> dict:
        """Validate GR import rows without inserting. Returns annotated rows."""
        try:
            from sc_gr_app.services import import_service
            payload = self._required_payload(payload)
            rows = _require_payload_field(payload, "rows")
            if not isinstance(rows, list) or len(rows) == 0:
                return fail(ValidationError("rows must be a non-empty list"))
            preview = import_service.preview_gr_import(self.config, rows)
            return ok({"rows": preview})
        except PermissionDenied as e:
            return fail(e)
        except ValidationError as e:
            return fail(e)
```

- [ ] **Step 4: Update SC template — hints and add info row**

In `download_sc_template` (line 1626), update the `hints` list:

```python
# Replace line 1635-1640:
hints = ["Optional (auto-generated if empty)", "Required",
         "Optional (defaults to importer)",
         "material/service/fixed_asset/FC", "Cost center number",
         "Required (e.g. 50000)", "YYYY-MM-DD", "YYYY-MM-DD",
         "approved/finished", "Optional",
         "CNY/EUR/USD", "Optional (FC only)"]
```

And add the info row. The current template has rows r=1 (headers), r=2 (hints), r=3 (sample). We need to shift all to r=2/r=3/r=4 and add r=1 as a merged info cell.

**Note:** The `_inline_str_cell`, `_xml_escape`, and `_col_letter` helper functions are defined above the replacement point inside the same method and remain available — only the sheet_xml construction block is being replaced.

Replace the sheet_xml construction (lines 1666-1673) with:

```python
        # Shift existing rows down by 1 to make room for info row
        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only SC records with status \"approved\" or \"finished\" can be imported. "
            "Required fields: SC NO, SC Amount, Status. "
            "Leave SC ID empty to auto-generate."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
</worksheet>"""
```

- [ ] **Step 5: Update PO template — hints and add info row**

In `download_po_template` (line 1721), update the `hints` list:

```python
# Replace lines 1731-1736:
hints = ["Optional (auto-generated if empty)", "Required (must exist)",
         "Optional (must exist if provided)",
         "Required", "Optional (defaults to importer)", "Required",
         "active/finished", "YYYY-MM-DD", "YYYY-MM-DD", "Optional",
         "monthly/quarterly/yearly", "Optional", "Optional", "Optional",
         "Optional"]
```

Shift rows and add merged info row (same pattern as SC, using PO info text):

```python
        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only PO records with status \"active\" or \"finished\" can be imported. "
            "Required fields: SC ID, PO NO, PO Amount, Status. "
            "Leave PO ID empty to auto-generate."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
</worksheet>"""
```

- [ ] **Step 6: Update GR template — hints and add info row**

In `download_gr_template` (line 1816), update the `hints` list:

```python
# Replace lines 1826-1831:
hints = ["Optional (auto-generated if empty)", "Required (must exist)",
         "Required", "Optional (defaults to importer)",
         "Required", "Required",
         "approved/finished", "Optional",
         "Optional (e.g. 13)", "Optional", "Optional", "Optional",
         "Required (YYYY-MM-DD)", "Required (YYYY-MM-DD)", "YYYY-MM-DD"]
```

And update the sample row:

```python
# Replace lines 1832-1835:
sample = ["[EXAMPLE]", "PO-0000000-20260601-001", "", "",
          "10000", "10000", "approved", "", "13",
          "", "Sample goods description", "",
          "2026-01-01", "2026-12-31", ""]
```

Shift rows and add merged info row:

```python
        header_cells = "".join(_inline_str_cell(i, 2, h) for i, h in enumerate(headers))
        hint_cells = "".join(_inline_str_cell(i, 3, h) for i, h in enumerate(hints))
        sample_cells = "".join(_inline_str_cell(i, 4, v) for i, v in enumerate(sample))

        last_col = _col_letter(len(headers) - 1)
        info_text = (
            "Import Rules: Only GR records with status \"approved\" or \"finished\" can be imported. "
            "Required fields: PO ID, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. "
            "Leave GR ID empty to auto-generate."
        )
        info_cell = f'<c r="A1" t="inlineStr"><is><t>{_xml_escape(info_text)}</t></is></c>'

        sheet_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <mergeCells count="1"><mergeCell ref="A1:{last_col}1"/></mergeCells>
  <sheetData>
    <row r="1">{info_cell}</row>
    <row r="2">{header_cells}</row>
    <row r="3">{hint_cells}</row>
    <row r="4">{sample_cells}</row>
  </sheetData>
</worksheet>"""
```

- [ ] **Step 7: Run tests to verify no regressions**

```
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add sc_gr_app/api/bridge.py
git commit -m "feat: add preview import endpoints and update templates with info rows"
```

---

### Task 5: Add i18n keys

**Files:**
- Modify: `frontend/src/i18n/locales/en-US.js` (line 80 `common` section, line 236 before `po`, line 297 before `gr`, line 376 before `vendor`)
- Modify: `frontend/src/i18n/locales/zh-CN.js` (same line numbers)

- [ ] **Step 1: Add common import keys to en-US.js**

In `frontend/src/i18n/locales/en-US.js`, add to the `common` section (before line 80 `},`):

```javascript
    importValid: 'Valid: {n}',
    importInvalid: 'Invalid: {n}',
    importSelected: 'Selected: {n}',
    importReSelect: 'Re-select',
    importConfirm: 'Import ({n})',
    importFile: 'File',
    importSelectFile: 'Select file',
    importDropHint: 'Drop file here or click to upload',
    importFormatHint: 'Only .xlsx/.xls files',
    importValidation: 'Validation',
    template: 'Template',
```

- [ ] **Step 2: Add sc.importRules to en-US.js**

In `frontend/src/i18n/locales/en-US.js`, add at the end of the `sc` section (before line 236 `},`):

```javascript
    currency: 'Currency',
    importRules: 'Only SC records with status "Approved" or "Finished" can be imported. Required fields: SC NO, SC Amount, Status. Leave SC ID empty to auto-generate.',
  },
```

- [ ] **Step 3: Add po.importRules to en-US.js**

In `frontend/src/i18n/locales/en-US.js`, add at the end of the `po` section (before line 297 `},`):

```javascript
    draftSaved: 'Draft saved',
    importRules: 'Only PO records with status "Active" or "Finished" can be imported. Required fields: SC ID, PO NO, PO Amount, Status. Leave PO ID empty to auto-generate.',
  },
```

- [ ] **Step 4: Add gr.importRules to en-US.js**

In `frontend/src/i18n/locales/en-US.js`, add at the end of the `gr` section (before line 376 `},`):

```javascript
    grSubmitted: 'GR submitted',
    importRules: 'Only GR records with status "Approved" or "Finished" can be imported. Required fields: PO ID, GR NO, Estimated Amount, Con Value, Delivery From, Delivery To, Status. Leave GR ID empty to auto-generate.',
  },
```

- [ ] **Step 5: Add common import keys to zh-CN.js**

In `frontend/src/i18n/locales/zh-CN.js`, add to the `common` section:

```javascript
    importValid: '有效: {n}',
    importInvalid: '无效: {n}',
    importSelected: '已选: {n}',
    importReSelect: '重新选择',
    importConfirm: '确认导入 ({n})',
    importFile: '文件',
    importSelectFile: '选择文件',
    importDropHint: '将文件拖到此处或点击上传',
    importFormatHint: '仅支持 .xlsx/.xls 文件',
    importValidation: '校验结果',
    template: '模板',
```

- [ ] **Step 6: Add sc.importRules to zh-CN.js**

In `frontend/src/i18n/locales/zh-CN.js`, add at the end of the `sc` section:

```javascript
    currency: '币种',
    importRules: '仅允许导入状态为"Approved（已审批）"或"Finished（已完成）"的SC记录。必填字段：SC NO（SC编号）、SC Amount（SC金额）、Status（状态）。SC ID留空将自动生成。',
  },
```

- [ ] **Step 7: Add po.importRules to zh-CN.js**

In `frontend/src/i18n/locales/zh-CN.js`, add at the end of the `po` section:

```javascript
    draftSaved: '草稿已保存',
    importRules: '仅允许导入状态为"Active（进行中）"或"Finished（已完成）"的PO记录。必填字段：SC ID（关联SC编号）、PO NO（PO编号）、PO Amount（PO金额）、Status（状态）。PO ID留空将自动生成。',
  },
```

- [ ] **Step 8: Add gr.importRules to zh-CN.js**

In `frontend/src/i18n/locales/zh-CN.js`, add at the end of the `gr` section:

```javascript
    grSubmitted: 'GR已提交',
    importRules: '仅允许导入状态为"Approved（已审批）"或"Finished（已完成）"的GR记录。必填字段：PO ID（关联PO编号）、GR NO（GR编号）、Estimated Amount（预估金额）、Con Value（合同金额）、Delivery From（交付开始日期）、Delivery To（交付结束日期）、Status（状态）。GR ID留空将自动生成。',
  },
```

- [ ] **Step 9: Commit**

```bash
git add frontend/src/i18n/locales/en-US.js frontend/src/i18n/locales/zh-CN.js
git commit -m "feat: add i18n keys for import rules and preview UI"
```

---

### Task 6: Create ImportPreviewDialog component

**Files:**
- Create: `frontend/src/components/common/ImportPreviewDialog.vue`

- [ ] **Step 1: Write the component**

```vue
<template>
  <el-dialog
    :model-value="visible"
    :title="'Import ' + entityType"
    width="1000px"
    top="3vh"
    @close="handleClose"
  >
    <!-- Step 1: File selection -->
    <div v-if="!preview" style="text-align:center;padding:20px 0">
      <el-alert type="info" :closable="false" style="margin-bottom:20px;text-align:left">
        {{ rulesText }}
      </el-alert>

      <el-button type="primary" plain @click="handleDownloadTemplate" style="margin-bottom:16px">
        <el-icon><Download /></el-icon> {{ $t('common.template') || 'Template' }}
      </el-button>

      <el-upload
        :auto-upload="false"
        :on-change="handleFileSelect"
        :limit="1"
        accept=".xlsx,.xls"
        drag
      >
        <el-icon :size="40"><UploadFilled /></el-icon>
        <div>{{ $t('common.importDropHint') }}</div>
        <template #tip>
          <div>{{ $t('common.importFormatHint') }}</div>
        </template>
      </el-upload>
    </div>

    <!-- Step 2: Preview -->
    <div v-else>
      <div style="margin-bottom:12px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
        <span style="font-size:13px;color:#475569">
          {{ $t('common.importFile') }}: <b>{{ fileName }}</b>
        </span>
        <el-tag size="small" type="success">{{ $t('common.importValid', { n: validCount }) }}</el-tag>
        <el-tag v-if="invalidCount > 0" size="small" type="danger">{{ $t('common.importInvalid', { n: invalidCount }) }}</el-tag>
        <el-tag size="small" type="info">{{ $t('common.importSelected', { n: selectedCount }) }}</el-tag>
      </div>

      <el-table
        ref="tableRef"
        :data="preview"
        max-height="420"
        stripe
        border
        size="small"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="40" :selectable="rowSelectable" />
        <el-table-column type="index" width="45" :label="'#'" />
        <el-table-column
          v-for="col in columns"
          :key="col.prop"
          :prop="col.prop"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth"
        >
          <template #default="{ row }">
            <span :style="{ color: row._valid ? '' : '#c0c4cc' }">{{ row[col.prop] || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="$t('common.importValidation') || 'Validation'" width="180">
          <template #default="{ row }">
            <div v-if="row._errors && row._errors.length > 0" style="color:#f56c6c;font-size:12px">
              <span v-for="err in row._errors" :key="err" style="display:block">&#10007; {{ err }}</span>
            </div>
            <span v-else style="color:#67c23a">&#10003; Valid</span>
          </template>
        </el-table-column>
      </el-table>

      <div v-if="importResult" style="margin-top:16px">
        <el-alert
          v-if="importResult.ok"
          type="success"
          :closable="false"
        >
          <template #title>
            Imported {{ importResult.count }} records
            <span v-if="importResult.skipped_duplicate > 0">({{ importResult.skipped_duplicate }} duplicates skipped)</span>
          </template>
        </el-alert>
        <el-alert v-else type="error" :closable="false">
          <template #title>
            <div v-for="e in importResult.errors" :key="e.row">Row {{ e.row }}: {{ e.field }} - {{ e.message }}</div>
          </template>
        </el-alert>
      </div>
    </div>

    <template #footer>
      <div v-if="!preview">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
      </div>
      <div v-else-if="!importResult">
        <el-button @click="handleClose">{{ $t('common.cancel') }}</el-button>
        <el-button @click="handleReselect">{{ $t('common.importReSelect') }}</el-button>
        <el-button type="primary" @click="handleImport" :loading="importing" :disabled="selectedCount === 0">
          {{ $t('common.importConfirm', { n: selectedCount }) }}
        </el-button>
      </div>
      <div v-else>
        <el-button type="primary" @click="handleDone">{{ $t('common.confirm') }}</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download, UploadFilled } from '@element-plus/icons-vue'
import { callApi } from '@/api/bridge.js'
import { ElMessage } from 'element-plus'
import * as XLSX from 'xlsx'

const { t } = useI18n()

const props = defineProps({
  visible: { type: Boolean, default: false },
  entityType: { type: String, required: true },
  columns: { type: Array, required: true },
  rulesText: { type: String, default: '' },
})

const emit = defineEmits(['update:visible', 'imported'])

const loading = ref(false)
const importing = ref(false)
const preview = ref(null)
const fileName = ref('')
const importResult = ref(null)
const tableRef = ref(null)
const selectedRows = ref([])

const validCount = computed(() =>
  preview.value ? preview.value.filter(r => r._valid).length : 0
)
const invalidCount = computed(() =>
  preview.value ? preview.value.filter(r => !r._valid).length : 0
)
const selectedCount = computed(() => selectedRows.value.length)

function rowSelectable(row) {
  return row._valid === true
}

function handleSelectionChange(selection) {
  selectedRows.value = selection
}

async function handleDownloadTemplate() {
  try {
    const result = await callApi(`download_${props.entityType.toLowerCase()}_template`)
    const saveResult = await callApi('save_file', { filename: result.filename, data: result.data })
    if (saveResult?.cancelled) return
    ElMessage.success('Template downloaded')
  } catch (e) {
    ElMessage.error(e.message || 'Failed to download template')
  }
}

async function handleFileSelect(uploadFile) {
  const file = uploadFile.raw
  if (!file) {
    ElMessage.error('No file selected')
    return
  }
  loading.value = true
  fileName.value = file.name
  try {
    const data = await file.arrayBuffer()
    const wb = XLSX.read(data, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rows = XLSX.utils.sheet_to_json(ws, { defval: '' })
    const previewMethod = `preview_${props.entityType.toLowerCase()}_import`
    const result = await callApi(previewMethod, { rows })
    preview.value = result.rows
    // Select all valid rows by default
    await nextTick()
    if (tableRef.value) {
      preview.value.forEach((row, idx) => {
        if (row._valid) {
          tableRef.value.toggleRowSelection(row, true)
        }
      })
    }
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    loading.value = false
  }
}

async function handleImport() {
  importing.value = true
  try {
    const cleanRows = selectedRows.value.map(r => {
      const { _errors, _valid, ...rest } = r
      return rest
    })
    const importMethod = `import_${props.entityType.toLowerCase()}s`
    importResult.value = await callApi(importMethod, { rows: cleanRows })
  } catch (e) {
    ElMessage.error(e.message)
  } finally {
    importing.value = false
  }
}

function handleReselect() {
  preview.value = null
  fileName.value = ''
  importResult.value = null
  selectedRows.value = []
}

function handleDone() {
  emit('imported')
  handleClose()
}

function handleClose() {
  preview.value = null
  fileName.value = ''
  importResult.value = null
  selectedRows.value = []
  emit('update:visible', false)
}

watch(() => props.visible, (newVal) => {
  if (!newVal) {
    preview.value = null
    fileName.value = ''
    importResult.value = null
    selectedRows.value = []
  }
})
</script>
```

Wait — `nextTick` needs to be imported. Add it to the import:

```javascript
import { ref, computed, nextTick, watch } from 'vue'
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/common/ImportPreviewDialog.vue
git commit -m "feat: add reusable ImportPreviewDialog component"
```

---

### Task 7: Replace import dialogs in ScListView, PoListView, GrListView

**Files:**
- Modify: `frontend/src/views/ScListView.vue` (lines 68-91, 318-338)
- Modify: `frontend/src/views/PoListView.vue` (lines 79-101, 331-351)
- Modify: `frontend/src/views/GrListView.vue` (lines 126-148, 431-451)

- [ ] **Step 1: Replace ScListView import dialog**

In `frontend/src/views/ScListView.vue`, replace the `<el-dialog>` block (lines 68-91):

```vue
    <ImportPreviewDialog
      v-model:visible="importVisible"
      entity-type="SC"
      :columns="scImportColumns"
      :rules-text="$t('sc.importRules')"
      @imported="searchScs"
    />
```

Remove the old import JS code (lines 318-338):

```javascript
// Remove:
// SC import
const importVisible = ref(false)
const importResult = ref(null)

async function handleFileSelect(uploadFile) { ... }

async function downloadTemplate() { ... }
```

Replace with:

```javascript
// SC import
const importVisible = ref(false)

const scImportColumns = [
  { prop: 'sc_id', label: 'SC ID', width: '160' },
  { prop: 'sc_no', label: t('sc.scNo'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'request_type', label: t('sc.requestType'), width: '100' },
  { prop: 'cost_center', label: t('sc.costCenter'), width: '100' },
  { prop: 'sc_amount', label: t('sc.scAmount'), width: '100' },
  { prop: 'service_period_start', label: t('sc.servicePeriodStart'), width: '110' },
  { prop: 'service_period_end', label: t('sc.servicePeriodEnd'), width: '110' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'description', label: t('common.description'), minWidth: '140' },
  { prop: 'currency', label: t('sc.currency'), width: '70' },
  { prop: 'internal_system_number', label: t('sc.internalSystemNumber'), width: '100' },
]
```

Add the import at the top of the script section:

```javascript
import ImportPreviewDialog from '@/components/common/ImportPreviewDialog.vue'
```

Remove the `XLSX` import if it's no longer needed (check if it's used elsewhere in the file — if not, remove `import * as XLSX from 'xlsx'`).

Remove the `UploadFilled` icon import if no longer used.

**Important:** Do NOT remove the `downloadTemplate()` function — it is used by the Template toolbar button in the template and is separate from the import dialog. Only the old `handleFileSelect()`, `importResult`, and any now-unused imports should be removed.

- [ ] **Step 2: Replace PoListView import dialog**

In `frontend/src/views/PoListView.vue`, replace the `<el-dialog>` block (lines 79-101):

```vue
    <ImportPreviewDialog
      v-model:visible="importVisible"
      entity-type="PO"
      :columns="poImportColumns"
      :rules-text="$t('po.importRules')"
      @imported="searchPos"
    />
```

Remove the old import JS code (lines 331-351) and replace with:

```javascript
// PO import
const importVisible = ref(false)

const poImportColumns = [
  { prop: 'po_id', label: 'PO ID', width: '160' },
  { prop: 'sc_id', label: 'SC ID', width: '160' },
  { prop: 'vendor_id', label: t('po.vendor'), width: '100' },
  { prop: 'po_no', label: t('po.poNo'), width: '120' },
  { prop: 'requester_id', label: t('sc.requester'), width: '100' },
  { prop: 'po_amount', label: t('po.poAmount'), width: '100' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'contract_from', label: t('po.contractFrom'), width: '110' },
  { prop: 'contract_to', label: t('po.contractTo'), width: '110' },
  { prop: 'contract_no', label: t('po.contractNo'), width: '120' },
  { prop: 'payment_frequency', label: t('po.paymentFrequency'), width: '100' },
  { prop: 'contract_pos', label: t('po.contractPos'), width: '90' },
  { prop: 'contract_type', label: t('po.contractType'), width: '100' },
  { prop: 'cost_center', label: t('po.costCenter'), width: '100' },
  { prop: 'purchaser', label: t('po.purchaser'), width: '100' },
]
```

Add the import and clean up unused imports (same pattern as ScListView).

- [ ] **Step 3: Replace GrListView import dialog**

In `frontend/src/views/GrListView.vue`, replace the `<el-dialog>` block (lines 126-148):

```vue
    <ImportPreviewDialog
      v-model:visible="importVisible"
      entity-type="GR"
      :columns="grImportColumns"
      :rules-text="$t('gr.importRules')"
      @imported="searchGrs"
    />
```

Remove the old import JS code (lines 431-451) and replace with:

```javascript
// GR import
const importVisible = ref(false)

const grImportColumns = [
  { prop: 'gr_id', label: 'GR ID', width: '160' },
  { prop: 'po_id', label: 'PO ID', width: '160' },
  { prop: 'gr_no', label: t('gr.grNo'), width: '120' },
  { prop: 'requester_id', label: t('gr.requester'), width: '100' },
  { prop: 'estimated_amount', label: t('gr.estimatedAmount'), width: '110' },
  { prop: 'con_value', label: t('gr.conValue'), width: '110' },
  { prop: 'status', label: t('common.status'), width: '90' },
  { prop: 'remark', label: t('gr.remark'), width: '120' },
  { prop: 'tax_rate', label: t('gr.taxRate'), width: '70' },
  { prop: 'gross_cost', label: t('gr.grossCost'), width: '100' },
  { prop: 'goods_service_description', label: t('gr.goodsServiceDescription'), minWidth: '140' },
  { prop: 'confirmation_name', label: t('gr.confirmationName'), width: '120' },
  { prop: 'delivery_from', label: t('gr.deliveryFrom'), width: '110' },
  { prop: 'delivery_to', label: t('gr.deliveryTo'), width: '110' },
  { prop: 'last_delivery', label: t('gr.lastDelivery'), width: '110' },
]
```

Add the import and clean up unused imports.

- [ ] **Step 4: Run the full test suite**

```
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/views/ScListView.vue frontend/src/views/PoListView.vue frontend/src/views/GrListView.vue
git commit -m "feat: replace inline import dialogs with ImportPreviewDialog in list views"
```

---

### Task 8: Final verification and commit

- [ ] **Step 1: Run all tests**

```
uv run pytest -q
```

Expected: All tests pass.

- [ ] **Step 2: Verify the app starts**

```
uv run python -m sc_gr_app.main
```

Check that the app launches without import errors. The frontend should compile and serve.

- [ ] **Step 3: Final commit (if any cleanup needed)**

```bash
git status
```
