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
        "request_type": "new",
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


_gr_counter = 0


def _create_gr(app_config, current_user, po_id, admin, status="approved",
               last_delivery=None, estimated_amount=1000):
    """Create a GR with a given status. Returns GR dict.

    Starts from draft and runs lifecycle transitions -- submit_gr requires draft status.
    Uses module-level imports (create_gr, submit_gr, confirm_gr, approve_gr
    already imported at top).
    admin must be a real user dict from the DB (used for confirm/approve steps).
    """
    global _gr_counter
    _gr_counter += 1
    data = {
        "po_id": po_id,
        "requester_id": current_user["user_id"],
        "estimated_amount": estimated_amount,
        "gr_no": f"GR-NO-TEST-{status}-{_gr_counter}",
        "status": "draft",  # must start from draft -- submit_gr requires draft status
    }
    if last_delivery is not None:
        data["last_delivery"] = last_delivery

    gr = create_gr(app_config, current_user, data)
    if status in ("manager_confirm", "pending", "approved"):
        gr = submit_gr(app_config, current_user, gr["gr_id"])
    if status in ("pending", "approved"):
        gr = confirm_gr(app_config, admin, gr["gr_id"])
    if status == "approved":
        gr = approve_gr(app_config, admin, gr["gr_id"], con_value=estimated_amount)
    return gr


def _create_finished_gr(app_config, admin, user, po_id, last_delivery=None):
    """Create and finish a GR. Returns GR dict."""
    gr = _create_gr(app_config, user, po_id, admin, status="approved", last_delivery=last_delivery)
    return finish_gr(app_config, user, gr["gr_id"])


def _create_denied_gr(app_config, admin, user, po_id, last_delivery=None):
    """Create and deny a GR. Returns GR dict."""
    gr = _create_gr(app_config, user, po_id, admin, status="pending", last_delivery=last_delivery)
    return deny_gr(app_config, admin, gr["gr_id"])


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


class TestGrUpdate:
    def test_update_gr_remark(self, seeded_config):
        """update_gr can change remark on a pending GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = update_gr(seeded_config, admin, gr["gr_id"], {
            "remark": "Updated remark",
        })
        assert result["remark"] == "Updated remark"

    def test_update_gr_rejects_finished_gr(self, seeded_config):
        """Cannot update a finished GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        gr = approve_gr(seeded_config, admin, gr["gr_id"], con_value=10000)
        gr = finish_gr(seeded_config, admin, gr["gr_id"])
        with pytest.raises(ConflictError, match="GR cannot be edited in its current status"):
            update_gr(seeded_config, admin, gr["gr_id"], {"remark": "test"})

    def test_update_gr_estimated_amount(self, seeded_config):
        """update_gr can change estimated_amount."""
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
    def test_deny_pending_gr(self, seeded_config):
        """Deny a pending GR transitions to denied."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = deny_gr(seeded_config, admin, gr["gr_id"])
        assert result["status"] == "denied"

    def test_deny_rejects_already_denied(self, seeded_config):
        """Denying an already denied GR raises ConflictError."""
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
        """Non-admin cannot deny a GR."""
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
        """Finish an approved GR transitions to finished."""
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
        """Cannot finish a GR that is not approved."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="GR must be approved"):
            finish_gr(seeded_config, admin, gr["gr_id"])


class TestGrRecall:
    def test_recall_pending_gr(self, seeded_config):
        """SC requester recalling a pending GR returns it to draft."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        result = recall_gr(seeded_config, requester, gr["gr_id"])
        assert result["status"] == "draft"

    def test_recall_rejects_non_manager_confirm_or_pending(self, seeded_config):
        """Cannot recall a GR that is not manager_confirm or pending."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        with pytest.raises(ConflictError, match="Only manager_confirm or pending GR can be recalled"):
            recall_gr(seeded_config, requester, gr["gr_id"])

    def test_recall_requires_sc_requester(self, seeded_config):
        """Non-requester cannot recall a GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(PermissionDenied, match="Only the SC requester can recall"):
            recall_gr(seeded_config, admin, gr["gr_id"])


class TestGrDelete:
    def test_delete_draft_gr(self, seeded_config):
        """Deleting a draft GR succeeds and returns the deleted GR record."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        result = delete_gr(seeded_config, admin, gr["gr_id"])
        assert result["gr_id"] == gr["gr_id"]
        assert result["status"] == "draft"

    def test_delete_rejects_non_draft(self, seeded_config):
        """Cannot delete a non-draft GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
        })
        with pytest.raises(ConflictError, match="Only draft GR can be deleted"):
            delete_gr(seeded_config, admin, gr["gr_id"])

    def test_delete_requires_gr_owner_or_admin(self, seeded_config):
        """Non-owner cannot delete a GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = create_gr(seeded_config, admin, {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 10000,
            "status": "draft",
        })
        other = {"user_id": "U2", "role": "requester", "machine_id": "M3"}
        with pytest.raises(PermissionDenied):
            delete_gr(seeded_config, other, gr["gr_id"])


class TestGrValidation:
    def test_draft_po_allows_only_draft_gr(self, seeded_config):
        """GR creation under draft PO fails if status is not draft."""
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
        """Creating GR with estimated_amount exceeding SC available amount fails."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        with pytest.raises(ConflictError, match="SC available amount is insufficient"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 999999,
            })

    def test_gr_creation_fails_when_po_open_amount_insufficient(self, seeded_config):
        """Creating GR with estimated_amount exceeding PO open amount fails."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        with pytest.raises(ConflictError, match="PO open amount is insufficient"):
            create_gr(seeded_config, admin, {
                "po_id": po["po_id"],
                "requester_id": requester["user_id"],
                "estimated_amount": 99999,
            })


class TestLastDeliveryUniqueness:
    def test_create_gr_with_ld_no_conflict(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        assert gr["last_delivery"] == "Y"

    def test_create_gr_with_ld_conflict(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        with pytest.raises(ConflictError, match="already marked as Last Delivery"):
            _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")

    def test_create_gr_with_ld_denied_excluded(self, seeded_config):
        """Denied GR with LD should not block new LD GR."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr1 = _create_gr(seeded_config, requester, po["po_id"], admin,
                         last_delivery="Y", status="pending")
        deny_gr(seeded_config, admin, gr1["gr_id"])
        gr2 = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        assert gr2["last_delivery"] == "Y"

    def test_create_gr_invalid_last_delivery_value(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        data = {
            "po_id": po["po_id"],
            "requester_id": requester["user_id"],
            "estimated_amount": 1000,
            "last_delivery": "yes",
        }
        with pytest.raises(ValidationError, match="must be 'Y' or 'N'"):
            create_gr(seeded_config, requester, data)

    def test_update_gr_set_ld_conflict(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr1 = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        gr2 = _create_gr(seeded_config, requester, po["po_id"], admin)
        with pytest.raises(ConflictError, match="already marked as Last Delivery"):
            update_gr(seeded_config, requester, gr2["gr_id"], {"last_delivery": "Y"})

    def test_update_gr_unset_ld_allowed(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        updated = update_gr(seeded_config, requester, gr["gr_id"], {"last_delivery": "N"})
        assert updated["last_delivery"] == "N"


class TestLastDeliveryCascadeFinish:
    def test_finish_non_ld_gr_normal(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = _create_gr(seeded_config, requester, po["po_id"], admin)
        result = finish_gr(seeded_config, requester, gr["gr_id"])
        assert result["status"] == "finished"
        # PO should NOT be finished
        with connect(seeded_config) as conn:
            po_status = conn.execute(
                "SELECT status FROM pos WHERE po_id = ?", (po["po_id"],)
            ).fetchone()
            assert po_status["status"] == "active"

    def test_finish_ld_gr_needs_cascade(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        gr_other = _create_gr(seeded_config, requester, po["po_id"], admin)
        result = finish_gr(seeded_config, requester, gr_ld["gr_id"])
        assert result["needs_cascade"] is True
        assert gr_other["gr_id"] in result["grs_to_finish"]

    def test_finish_ld_gr_cascade_empty_needs_confirm(self, seeded_config):
        """LD GR with all others already finished -- still needs confirmation."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        _create_finished_gr(seeded_config, admin, requester, po["po_id"])
        result = finish_gr(seeded_config, requester, gr_ld["gr_id"])
        assert result["needs_cascade"] is True
        assert result["grs_to_finish"] == []

    def test_finish_ld_gr_problematic_blocks(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        gr_pending = _create_gr(seeded_config, requester, po["po_id"], admin, status="pending")
        with pytest.raises(ConflictError) as exc:
            finish_gr(seeded_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None
        conflict_ids = [c["gr_id"] for c in exc.value.conflicts]
        assert gr_pending["gr_id"] in conflict_ids

    def test_finish_ld_gr_denied_blocks(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        _create_denied_gr(seeded_config, admin, requester, po["po_id"])
        with pytest.raises(ConflictError) as exc:
            finish_gr(seeded_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None

    def test_finish_ld_gr_cascade_success(self, seeded_config):
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        gr_other = _create_gr(seeded_config, requester, po["po_id"], admin)

        result = finish_gr(seeded_config, requester, gr_ld["gr_id"], confirm_cascade=True)
        assert result["gr"]["status"] == "finished"
        assert gr_other["gr_id"] in result["cascaded_grs"]
        assert result["po_finished"] == po["po_id"]

        # Verify all GRs and PO are finished with finished_by set
        with connect(seeded_config) as conn:
            for gr_id in [gr_ld["gr_id"], gr_other["gr_id"]]:
                gr = conn.execute(
                    "SELECT status, finished_by, finished_at FROM gr_requests WHERE gr_id = ?",
                    (gr_id,),
                ).fetchone()
                assert gr["status"] == "finished"
                assert gr["finished_by"] == requester["user_id"]
                assert gr["finished_at"] is not None
            po_row = conn.execute(
                "SELECT status, finished_by, finished_at FROM pos WHERE po_id = ?",
                (po["po_id"],),
            ).fetchone()
            assert po_row["status"] == "finished"
            assert po_row["finished_by"] == requester["user_id"]
            assert po_row["finished_at"] is not None

    def test_confirm_cascade_on_non_ld_gr_ignored(self, seeded_config):
        """confirm_cascade=True on non-LD GR silently ignored, normal finish."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr = _create_gr(seeded_config, requester, po["po_id"], admin)
        result = finish_gr(seeded_config, requester, gr["gr_id"], confirm_cascade=True)
        assert result["status"] == "finished"
        assert "gr" not in result  # plain dict, not cascade wrapper

    def test_problematic_priority_over_approved(self, seeded_config):
        """When both problematic and approved GRs exist, problematic takes priority."""
        admin, requester, sc, po = _setup_approved_sc_with_active_po(seeded_config)
        gr_ld = _create_gr(seeded_config, requester, po["po_id"], admin, last_delivery="Y")
        _create_gr(seeded_config, requester, po["po_id"], admin)  # approved
        _create_gr(seeded_config, requester, po["po_id"], admin, status="pending")  # problematic

        with pytest.raises(ConflictError) as exc:
            finish_gr(seeded_config, requester, gr_ld["gr_id"])
        assert exc.value.conflicts is not None
