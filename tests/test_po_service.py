import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.po_service import create_po, update_po
from sc_gr_app.services.sc_service import add_sc_vendor, create_sc_draft
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
