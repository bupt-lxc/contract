"""Tests for import_service -- status restrictions, required fields, preview functions."""
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services import import_service
from datetime import datetime, timezone


def _utc_now():
    return datetime.now(timezone.utc).isoformat()


def _seed_user(conn, user_id="U000001", machine_id="M000001", role="requester"):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?)",
        (user_id, machine_id, f"User {user_id}", role, _utc_now(), _utc_now()),
    )
    conn.commit()


def _seed_sc(conn, sc_id="SC-0000001-20260701-001"):
    conn.execute(
        """INSERT OR IGNORE INTO sc_records (
               sc_id, sc_no, requester_id, request_type, cost_center,
               sc_amount, service_period_start, service_period_end,
               status, description, asset, created_by, created_at, updated_at
           ) VALUES (?, ?, 'U000001', 'service', 1000, 100000,
                     '2026-01-01', '2026-12-31',
                     'approved', 'Test SC', 'N', 'U000001', ?, ?)""",
        (sc_id, f"SCNO-{sc_id}", _utc_now(), _utc_now()),
    )
    conn.commit()


def _seed_po(conn, po_id="PO-0000001-20260701-001", sc_id="SC-0000001-20260701-001"):
    conn.execute(
        """INSERT OR IGNORE INTO pos (
               po_id, sc_id, po_no, vendor_id, requester_id, po_amount, status, created_at, updated_at
           ) VALUES (?, ?, ?, 'V000001', 'U000001', 50000, 'active', ?, ?)""",
        (po_id, sc_id, f"PONO-{po_id}", _utc_now(), _utc_now()),
    )
    conn.commit()


def _seed_vendor(conn):
    conn.execute(
        "INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('V000001', 'Test Vendor', 'IT', 'U000001', ?, ?)",
        (_utc_now(), _utc_now()),
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
                  "con_value": "10000", "status": "draft"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_rejects_pending_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "status": "pending"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_rejects_manager_confirm_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "status": "manager_confirm"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False

    def test_accepts_approved_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_accepts_finished_status(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_id": "PO-0000001-20260701-001", "gr_no": "GR-001", "estimated_amount": "10000",
                  "con_value": "10000", "status": "finished"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is True

    def test_gr_allows_missing_estimated_amount(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            self._seed_gr_deps(conn)
        rows = [{"po_no": "PONO-PO-0000001-20260701-001", "gr_no": "GR-OPT-001",
                  "con_value": "10000", "status": "approved"}]
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
                  "status": "approved"}]
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
                  "status": "approved"}]
        preview = import_service.preview_gr_import(app_config, rows)
        assert preview[0]["_valid"] is False
        assert any("con_value is required" in e for e in preview[0]["_errors"])


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
                  "con_value": "10000", "status": "approved"}]
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
        rows = [{"sc_no": "SC-CONFIRM", "sc_amount": "50000", "status": "approved",
                  "request_type": "service", "cost_center": "1000",
                  "service_period_start": "2026-01-01", "service_period_end": "2026-12-31"}]
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
        rows = [{"sc_id": "SC-0000001-20260701-001", "vendor_id": "V000001", "po_no": "PO-CONFIRM", "po_amount": "50000", "status": "active"}]
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
                  "con_value": "10000", "status": "approved"}]
        result = import_service.import_grs(app_config, current_user, rows)
        assert result["ok"] is True
        assert result["count"] == 1
