import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, ValidationError
from sc_gr_app.services.po_service import create_po, update_po
from sc_gr_app.services.sc_service import add_sc_vendor, approve_sc, confirm_sc, create_sc_draft, submit_sc
from sc_gr_app.services.user_service import seed_users
from sc_gr_app.services.vendor_service import create_vendor


class TestPoVendorRestriction:
    def test_create_po_rejects_unlinked_vendor(self, app_config):
        """PO creation must fail when vendor is not linked to the SC."""
        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())

        sc = create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
        })

        vendor = create_vendor(app_config, admin, {
            "vendor_id": "V999",
            "vendor_name": "Unlinked Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "K999",
        })

        with pytest.raises(ValidationError, match="not linked to SC"):
            create_po(app_config, admin, {
                "sc_id": sc["sc_id"],
                "vendor_id": vendor["vendor_id"],
                "po_amount": "1000",
            })

    def test_update_po_rejects_unlinked_vendor(self, app_config):
        """PO update must fail when changing to a vendor not linked to the SC."""
        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())

        sc = create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
        })

        v1 = create_vendor(app_config, admin, {
            "vendor_id": "V-A",
            "vendor_name": "Vendor A",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KA",
        })
        v2 = create_vendor(app_config, admin, {
            "vendor_id": "V-B",
            "vendor_name": "Vendor B",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KB",
        })

        add_sc_vendor(app_config, admin, sc["sc_id"], v1["vendor_id"])

        po = create_po(app_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v1["vendor_id"],
            "po_amount": "1000",
        })

        with pytest.raises(ValidationError, match="not linked to SC"):
            update_po(app_config, admin, po["po_id"], {
                "vendor_id": v2["vendor_id"],
            })

    def test_update_po_rejects_amount_below_manager_confirm_gr_usage(self, app_config):
        """PO amount cannot drop below usage of manager_confirm GRs."""
        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())

        sc = create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
        })

        v = create_vendor(app_config, admin, {
            "vendor_id": "V-TEST",
            "vendor_name": "Test Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KTEST",
        })
        add_sc_vendor(app_config, admin, sc["sc_id"], v["vendor_id"])
        submit_sc(app_config, admin, sc["sc_id"], {
            "sc_no": "SC-NO-001",
            "request_type": "service",
            "cost_center": "CC-001",
            "sc_amount": "500",
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        confirm_sc(app_config, admin, sc["sc_id"])
        approve_sc(app_config, admin, sc["sc_id"])

        po = create_po(app_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "500",
        })
        # Insert a manager_confirm GR worth 300
        with connect(app_config) as conn:
            conn.execute(
                """
                insert into gr_requests (
                  gr_id, po_id, requester_id, estimated_amount,
                  status, created_by, created_at
                ) values ('GR-MC', ?, ?, 300, 'manager_confirm', ?, ?)
                """,
                (po["po_id"], admin["user_id"], admin["user_id"],
                 "2026-05-19T00:00:00+00:00"),
            )
            conn.commit()

        with pytest.raises(ConflictError, match="PO amount cannot be below GR usage"):
            update_po(app_config, admin, po["po_id"], {"po_amount": "200"})
