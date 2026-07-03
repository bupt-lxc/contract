import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, ValidationError
from sc_gr_app.services.po_service import create_po, update_po, finish_po
from sc_gr_app.services.sc_service import add_sc_vendor, approve_sc, confirm_sc, create_sc_draft, finish_sc, submit_sc
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


class TestPoFcGuards:
    """Unit tests for FC PO guards: finish, update, recall, delete."""

    def _setup_fc_chain(self, app_config, po_amount=80000):
        """Create SC(FC) + PO(FC) + vendor. Returns (sc_fc, po_fc, vendor_id, admin)."""
        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())

        sc_fc = create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
        })
        submit_sc(app_config, admin, sc_fc["sc_id"], {
            "sc_no": "SC-FC-001",
            "request_type": "FC",
            "cost_center": "CC-001",
            "sc_amount": "100000",
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        confirm_sc(app_config, admin, sc_fc["sc_id"])
        approve_sc(app_config, admin, sc_fc["sc_id"])

        v = create_vendor(app_config, admin, {
            "vendor_id": "V-FC",
            "vendor_name": "FC Vendor",
            "service_scope": "General Service",
            "ksrm_vendor_code": "KFC",
        })
        add_sc_vendor(app_config, admin, sc_fc["sc_id"], v["vendor_id"])

        po_fc = create_po(app_config, admin, {
            "sc_id": sc_fc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": str(po_amount),
        })
        return sc_fc, po_fc, v["vendor_id"], admin

    def _create_calloff_sc(self, app_config, admin, po_fc_id, sc_amount=30000):
        """Create a call-off SC under the given PO(FC). Returns the SC dict."""
        sc = create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
            "calloff_po_id": po_fc_id,
        })
        submit_sc(app_config, admin, sc["sc_id"], {
            "sc_no": "SC-CO-001",
            "request_type": "material",
            "cost_center": "CC-001",
            "sc_amount": str(sc_amount),
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        return sc

    # --- finish_po tests ---

    def test_finish_fc_po_blocked_by_pending_calloff(self, app_config):
        """PO(FC) cannot finish while a pending call-off SC exists."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config)
        self._create_calloff_sc(app_config, admin, po_fc["po_id"])
        # call-off SC is in 'pending' status, not final

        with pytest.raises(ConflictError, match="call-off"):
            finish_po(app_config, admin, po_fc["po_id"])

    def test_finish_fc_po_blocked_by_approved_calloff(self, app_config):
        """PO(FC) cannot finish while an approved (non-final) call-off SC exists."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config)
        sc = self._create_calloff_sc(app_config, admin, po_fc["po_id"])
        confirm_sc(app_config, admin, sc["sc_id"])
        approve_sc(app_config, admin, sc["sc_id"])

        with pytest.raises(ConflictError, match="call-off"):
            finish_po(app_config, admin, po_fc["po_id"])

    def test_finish_fc_po_allowed_when_calloffs_final(self, app_config):
        """PO(FC) can finish when all call-off SCs are in final state."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config)
        sc = self._create_calloff_sc(app_config, admin, po_fc["po_id"])
        confirm_sc(app_config, admin, sc["sc_id"])
        approve_sc(app_config, admin, sc["sc_id"])
        # Finish the call-off SC first (needs vendor + PO finished too)
        add_sc_vendor(app_config, admin, sc["sc_id"], vendor_id)
        calloff_po = create_po(app_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": vendor_id,
            "po_amount": "20000",
        })
        finish_po(app_config, admin, calloff_po["po_id"])
        finish_sc(app_config, admin, sc["sc_id"])

        # Now PO(FC) should finish successfully
        po_fc = finish_po(app_config, admin, po_fc["po_id"])
        assert po_fc["status"] == "finished"

    # --- update_po tests ---

    def test_update_fc_po_amount_below_calloff_total(self, app_config):
        """PO(FC) amount cannot be reduced below allocated call-off SC total."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config, po_amount=80000)
        self._create_calloff_sc(app_config, admin, po_fc["po_id"], sc_amount=50000)

        with pytest.raises(ConflictError, match="PO amount cannot be below allocated call-off"):
            update_po(app_config, admin, po_fc["po_id"], {"po_amount": "40000"})

    def test_update_fc_po_amount_above_calloff_total_allowed(self, app_config):
        """PO(FC) amount can be reduced as long as it stays >= call-off total."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config, po_amount=80000)
        self._create_calloff_sc(app_config, admin, po_fc["po_id"], sc_amount=30000)

        updated = update_po(app_config, admin, po_fc["po_id"], {"po_amount": "50000"})
        assert updated["po_amount"] == 50000.0

    # --- recall_po tests ---

    def test_recall_fc_po_blocked_by_non_draft_calloff(self, app_config):
        """PO(FC) cannot be recalled if non-draft call-off SCs exist."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config)
        self._create_calloff_sc(app_config, admin, po_fc["po_id"])
        # call-off SC is pending (non-draft)

        from sc_gr_app.services.po_service import recall_po
        with pytest.raises(ConflictError, match="non-draft call-off"):
            recall_po(app_config, admin, po_fc["po_id"])

    def test_recall_fc_po_allowed_with_only_draft_calloffs(self, app_config):
        """PO(FC) can be recalled if only draft call-off SCs exist."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config)

        # Create a draft call-off SC (not submitted)
        create_sc_draft(app_config, admin, {
            "requester_id": admin["user_id"],
            "calloff_po_id": po_fc["po_id"],
        })

        from sc_gr_app.services.po_service import recall_po
        result = recall_po(app_config, admin, po_fc["po_id"])
        assert result["status"] == "draft"

    # --- delete_po tests ---

    def test_delete_fc_po_blocked_by_existing_calloff(self, app_config):
        """PO(FC) cannot be deleted if call-off SCs reference it (defense-in-depth)."""
        sc_fc, po_fc, vendor_id, admin = self._setup_fc_chain(app_config, po_amount=80000)
        from sc_gr_app.services.po_service import delete_po

        # Create draft PO(FC) via direct SQL (bypasses the call-off active requirement)
        with connect(app_config) as conn:
            conn.execute(
                "insert into pos (po_id, sc_id, vendor_id, po_no, po_amount, status, "
                "created_at, updated_at) "
                "values ('PO-FC-DEL', ?, ?, 'PO-FC-DEL-NO', 50000, 'draft', "
                "'2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
                (sc_fc["sc_id"], vendor_id),
            )
            conn.execute(
                "insert into sc_records (sc_id, sc_no, requester_id, request_type, cost_center, "
                "sc_amount, service_period_start, service_period_end, status, calloff_po_id, "
                "created_by, created_at, updated_at) "
                "values ('SC-DEL-TEST', 'SC-DEL-NO', ?, 'material', 1000, 10000, "
                "'2026-01-01', '2026-12-31', 'draft', 'PO-FC-DEL', "
                "?, '2026-05-19T00:00:00+00:00', '2026-05-19T00:00:00+00:00')",
                (admin["user_id"], admin["user_id"]),
            )
            conn.commit()

        with pytest.raises(ConflictError, match="existing call-off"):
            delete_po(app_config, admin, "PO-FC-DEL")


class TestPoCreate:
    def test_create_po_rejects_missing_required_fields(self, seeded_config):
        """create_po raises ValidationError when required fields are missing."""
        with connect(seeded_config) as conn:
            admin = dict(conn.execute(
                "select * from users where role = 'admin' limit 1"
            ).fetchone())
        with pytest.raises(ValidationError, match="is required"):
            create_po(seeded_config, admin, {})

    def test_create_po_rejects_non_positive_amount(self, seeded_config):
        """create_po raises ValidationError when po_amount is not positive."""
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
            "vendor_name": "Test Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])

        with pytest.raises(ValidationError, match="po_amount must be positive"):
            create_po(seeded_config, admin, {
                "sc_id": sc["sc_id"],
                "vendor_id": v["vendor_id"],
                "po_amount": "0",
            })

    def test_create_po_under_draft_sc_creates_draft(self, seeded_config):
        """PO created under draft SC gets 'draft' status."""
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
            "vendor_name": "Test Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        assert po["status"] == "draft"


class TestPoSubmit:
    def test_submit_draft_po_to_active(self, seeded_config):
        """Submit draft PO transitions to active."""
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
            "vendor_name": "Submit Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        # Create draft PO under draft SC first
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        assert po["status"] == "draft"
        # Submit SC (submit_po blocks while SC is still draft)
        # SC amount must be >= 2x PO amount because submit_po budget check
        # sums allocated_po_amount (which already includes this PO) + po_amount
        submit_sc(seeded_config, admin, sc["sc_id"], {
            "sc_no": "SC-PO-SUB",
            "request_type": "material",
            "cost_center": 1000,
            "sc_amount": 100000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        result = submit_po(seeded_config, admin, po["po_id"])
        assert result["status"] == "active"


class TestPoFinishNonFc:
    def test_finish_active_po(self, seeded_config):
        """Finish an active PO under approved SC."""
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
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Finish Vendor",
            "service_scope": "General Service",
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
        """Delete a draft PO under draft SC."""
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
            "vendor_name": "Delete PO Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        result = delete_po(seeded_config, admin, po["po_id"])
        # delete_po returns the deleted PO record (a dict)
        assert result is not None
        assert result["po_id"] == po["po_id"]

        # Verify PO no longer exists
        with connect(seeded_config) as conn:
            row = conn.execute(
                "select 1 from pos where po_id = ?", (po["po_id"],)
            ).fetchone()
        assert row is None


class TestPoRecallNonFc:
    def test_recall_active_po(self, seeded_config):
        """Recall an active PO back to draft."""
        from sc_gr_app.services.po_service import recall_po
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
            "cost_center": 1000,
            "sc_amount": 50000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        })
        sc = confirm_sc(seeded_config, admin, sc["sc_id"])
        sc = approve_sc(seeded_config, admin, sc["sc_id"])
        v = create_vendor(seeded_config, admin, {
            "vendor_name": "Recall PO Vendor",
            "service_scope": "General Service",
        })
        add_sc_vendor(seeded_config, admin, sc["sc_id"], v["vendor_id"])
        po = create_po(seeded_config, admin, {
            "sc_id": sc["sc_id"],
            "vendor_id": v["vendor_id"],
            "po_amount": "30000",
        })
        # recall_po requires the SC requester, not just any admin
        result = recall_po(seeded_config, requester, po["po_id"])
        assert result["status"] == "draft"
