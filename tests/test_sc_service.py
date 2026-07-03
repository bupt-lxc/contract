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


class TestScConfirm:
    def test_confirm_manager_confirm_to_pending(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-CONF",
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
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-MC",
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
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-FIN",
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        sc = finish_sc(seeded_config, admin, sc["sc_id"])
        with pytest.raises(ConflictError, match="Finished SC cannot be edited"):
            update_sc(seeded_config, admin, sc["sc_id"], {"sc_no": "SC-BAD"})

    def test_update_amount_cannot_go_below_po_allocation(self, seeded_config):
        admin, requester = _resolve_users(seeded_config)
        sc = create_sc_draft(seeded_config, admin, {
            "requester_id": requester["user_id"],
        })
        sc = submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-PO-AMT",
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
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