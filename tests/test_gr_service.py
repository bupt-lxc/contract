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
    sc = create_sc_draft(app_config, admin, {
        "requester_id": requester["user_id"],
    })
    sc = submit_sc(app_config, admin, sc["sc_id"], {
        "sc_no": "SC-TEST",
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


class TestGrConfirm:
    def test_confirm_manager_confirm_to_pending(self, seeded_config):
        """confirm_gr transitions manager_confirm status to pending."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        gr = submit_gr(seeded_config, admin, gr["gr_id"])
        assert gr["status"] == "manager_confirm"
        result = confirm_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "pending"

    def test_confirm_rejects_non_manager_confirm(self, seeded_config):
        """confirm_gr raises ConflictError when GR is not in manager_confirm status."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        # GR under active PO auto-creates as "pending", not manager_confirm
        with pytest.raises(ConflictError, match="GR must be in manager_confirm status"):
            confirm_gr(seeded_config, admin, gr["gr_id"])

    def test_confirm_requires_admin(self, seeded_config):
        """confirm_gr raises PermissionDenied when non-admin tries to confirm."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        gr = submit_gr(seeded_config, admin, gr["gr_id"])
        with pytest.raises(PermissionDenied):
            confirm_gr(seeded_config, requester, gr["gr_id"])


class TestGrApprove:
    def test_approve_gr_sets_con_value(self, seeded_config):
        """approve_gr sets con_value and transitions to approved."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = approve_gr(seeded_config, admin, gr["gr_id"], con_value=9500)
        assert result["status"] == "approved"
        assert result["con_value"] == 9500.0

    def test_approve_gr_null_con_value_auto_fills_from_gross_cost(self, seeded_config):
        """approve_gr auto-fills con_value from gross_cost when con_value is None."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        # con_value=None triggers auto-fill from gross_cost (which equals estimated_amount when tax_rate is None)
        result = approve_gr(seeded_config, admin, gr["gr_id"], con_value=None)
        assert result["status"] == "approved"
        assert result["con_value"] == 10000.0

    def test_approve_rejects_non_pending_gr(self, seeded_config):
        """approve_gr raises ConflictError for non-pending GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        with pytest.raises(ConflictError, match="GR must be pending"):
            approve_gr(seeded_config, admin, gr["gr_id"], con_value=5000)

    def test_approve_requires_admin(self, seeded_config):
        """approve_gr raises PermissionDenied for non-admin."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(PermissionDenied):
            approve_gr(seeded_config, requester, gr["gr_id"], con_value=5000)

    def test_approve_gr_rejects_manager_confirm(self, seeded_config):
        """approve_gr raises ConflictError when GR is in manager_confirm (not pending)."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        gr = submit_gr(seeded_config, admin, gr["gr_id"])
        assert gr["status"] == "manager_confirm"
        with pytest.raises(ConflictError, match="GR must be pending"):
            approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
