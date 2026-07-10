"""Integration tests for FC call-off flow: SC(FC) -> PO(FC) -> call-off SC -> PO -> GR."""
import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, ValidationError
from sc_gr_app.services.budget_service import compute_po_fc_budget, compute_sc_fc_budget
from sc_gr_app.services.gr_service import create_gr
from sc_gr_app.services.po_service import create_po, finish_po
from sc_gr_app.services.sc_service import (
    add_sc_vendor,
    approve_sc,
    create_sc,
)
from sc_gr_app.services.vendor_service import create_vendor

USER = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
ADMIN = {"user_id": "A1", "role": "admin", "machine_id": "M2"}


def seed_users(app_config):
    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "A1",
                "M2",
                "Admin",
                "admin",
                None,
                "active",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()


def _create_vendor_and_link(app_config, sc_id):
    """Create a vendor and link it to the given SC. Returns vendor_id."""
    v = create_vendor(
        app_config,
        USER,
        {
            "vendor_name": "Vendor FC",
            "service_scope": "General Service",
        },
    )
    vendor_id = v["vendor_id"]
    add_sc_vendor(app_config, ADMIN, sc_id, vendor_id)
    return vendor_id


def test_full_fc_calloff_flow(app_config):
    """SC(FC) -> PO(FC) -> call-off SC -> PO -> GR complete chain."""
    migrate(app_config)
    seed_users(app_config)

    # 1. Create SC(FC)
    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-001",
        "requester_id": USER["user_id"],
        "request_type": "FC",
        "cost_center": 1000,
        "sc_amount": 100000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    assert sc_fc["request_type"] == "FC"
    sc_fc = approve_sc(app_config, ADMIN, sc_fc["sc_id"])
    vendor_id = _create_vendor_and_link(app_config, sc_fc["sc_id"])

    # 2. Create PO(FC) -- requires approved SC(FC) for active status
    po_fc = create_po(app_config, ADMIN, {
        "sc_id": sc_fc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 80000,
    })
    assert po_fc["status"] == "active"

    # 3. Create call-off SC under PO(FC)
    calloff_sc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-001",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-06-30",
        "calloff_po_id": po_fc["po_id"],
    })
    assert calloff_sc["calloff_po_id"] == po_fc["po_id"]
    assert calloff_sc["request_type"] == "call_off"

    # 4. Approve call-off SC and link the same vendor
    calloff_sc = approve_sc(app_config, ADMIN, calloff_sc["sc_id"])
    add_sc_vendor(app_config, ADMIN, calloff_sc["sc_id"], vendor_id)

    # 5. Create regular PO under call-off SC
    regular_po = create_po(app_config, ADMIN, {
        "sc_id": calloff_sc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 30000,
    })

    # 6. Create GR under regular PO
    gr = create_gr(app_config, ADMIN, {
        "po_id": regular_po["po_id"],
        "requester_id": USER["user_id"],
        "estimated_amount": 10000,
    })
    assert gr["po_id"] == regular_po["po_id"]

    # 7. Verify FC PO budget
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 50000.0
    assert fc_budget["open_po_amount"] == 30000.0


def test_cannot_create_calloff_under_non_fc_po(app_config):
    """Reject call-off SC creation when parent PO is not an FC PO."""
    migrate(app_config)
    seed_users(app_config)

    sc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-REG-001",
        "requester_id": USER["user_id"],
        "request_type": "new",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
    })
    sc = approve_sc(app_config, ADMIN, sc["sc_id"])
    vendor_id = _create_vendor_and_link(app_config, sc["sc_id"])
    po = create_po(app_config, ADMIN, {
        "sc_id": sc["sc_id"],
        "vendor_id": vendor_id,
        "po_amount": 30000,
    })

    with pytest.raises(ValidationError, match="Call-off PO must belong to an FC-type SC"):
        create_sc(app_config, ADMIN, {
            "sc_no": "SC-CO-BAD",
            "requester_id": USER["user_id"],
            "request_type": "call_off",
            "cost_center": 1000,
            "sc_amount": 10000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-06-30",
            "calloff_po_id": po["po_id"],
        })


def test_cannot_create_gr_under_fc_po(app_config):
    """Reject GR creation under an FC PO."""
    migrate(app_config)
    seed_users(app_config)

    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-GR",
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

    with pytest.raises(ConflictError, match="Cannot create GR under an FC PO"):
        create_gr(app_config, ADMIN, {
            "po_id": po_fc["po_id"],
            "requester_id": USER["user_id"],
            "estimated_amount": 10000,
        })


def test_calloff_sc_amount_exceeds_po_fc_budget(app_config):
    """Reject call-off SC when total would exceed PO(FC) amount."""
    migrate(app_config)
    seed_users(app_config)

    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-BUDGET",
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
        "po_amount": 50000,
    })

    # First call-off uses 40000
    create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-FIRST",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 40000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    # Second call-off of 20000 exceeds remaining 10000
    with pytest.raises(ConflictError, match="Call-off SC total would exceed PO\\(FC\\) amount"):
        create_sc(app_config, ADMIN, {
            "sc_no": "SC-CO-SECOND",
            "requester_id": USER["user_id"],
            "request_type": "call_off",
            "cost_center": 1000,
            "sc_amount": 20000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "calloff_po_id": po_fc["po_id"],
        })


def test_po_fc_finish_blocked_by_calloff_sc(app_config):
    """PO(FC) cannot finish while call-off SCs are not in final state."""
    migrate(app_config)
    seed_users(app_config)

    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-FINISH",
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
    create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-OPEN",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })

    with pytest.raises(ConflictError, match="Cannot finish PO.*call-off"):
        finish_po(app_config, ADMIN, po_fc["po_id"])


def test_mixed_calloff_statuses_budget(app_config):
    """Call-off SCs with mixed statuses (approved + denied): allocated includes
    all call-offs; pending excludes denied ones."""
    from sc_gr_app.services.sc_service import deny_sc as deny_sc_fn

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
    co_approved = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-APPROVED",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    approve_sc(app_config, ADMIN, co_approved["sc_id"])

    # Create then deny a call-off SC (40000)
    co_denied = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-DENIED",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 40000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    deny_sc_fn(app_config, ADMIN, co_denied["sc_id"])

    # allocated_calloff_amount counts all call-off SCs (denied included)
    # pending_calloff_amount excludes denied (status not in approved/pending/manager_confirm)
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 70000.0  # 30000 + 40000
    assert fc_budget["pending_calloff_amount"] == 30000.0    # only approved
    assert fc_budget["open_po_amount"] == 10000.0            # 80000 - 70000


def test_denied_calloff_still_blocks_budget(app_config):
    """Denied call-off SCs still count against PO(FC) budget; new call-offs
    cannot exceed the remaining amount."""
    from sc_gr_app.services.sc_service import deny_sc as deny_sc_fn

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

    # Create then deny a call-off SC (50000 used of 80000 PO)
    co = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-REL",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 50000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    deny_sc_fn(app_config, ADMIN, co["sc_id"])

    # Denied SC still counts toward allocated total; remaining = 30000
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 50000.0
    assert fc_budget["open_po_amount"] == 30000.0

    # Creating a 40000 call-off would exceed remaining 30000
    with pytest.raises(ConflictError, match="Call-off SC total would exceed PO\\(FC\\) amount"):
        create_sc(app_config, ADMIN, {
            "sc_no": "SC-CO-EXCEED",
            "requester_id": USER["user_id"],
            "request_type": "call_off",
            "cost_center": 1000,
            "sc_amount": 40000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "calloff_po_id": po_fc["po_id"],
        })

    # But creating a call-off within the remaining budget should work
    new_co = create_sc(app_config, ADMIN, {
        "sc_no": "SC-CO-VALID",
        "requester_id": USER["user_id"],
        "request_type": "call_off",
        "cost_center": 1000,
        "sc_amount": 30000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "calloff_po_id": po_fc["po_id"],
    })
    assert new_co["calloff_po_id"] == po_fc["po_id"]


def test_internal_system_number_resolves_to_calloff_po_id(app_config):
    """Simulate import scenario: SC created with internal_system_number
    (PO NO) but no calloff_po_id. After POs exist, post-import UPDATE
    resolves the link."""
    from datetime import datetime, timezone

    migrate(app_config)
    seed_users(app_config)

    # 1. Create SC(FC) and PO(FC) - the parent framework
    sc_fc = create_sc(app_config, ADMIN, {
        "sc_no": "SC-FC-RESOLVE",
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
        "po_no": "7600-RESOLVE-TEST",
    })

    # 2. Insert call-off SC via raw SQL as if from import:
    #    internal_system_number set, but calloff_po_id is NULL
    ts = datetime.now(timezone.utc).isoformat()
    calloff_sc_id = f"SC-CO-RESOLVE-{ts[:10].replace('-','')}-001"
    with connect(app_config) as conn:
        conn.execute(
            """INSERT INTO sc_records (
                sc_id, sc_no, requester_id, request_type, cost_center,
                sc_amount, service_period_start, service_period_end,
                status, description, created_by, created_at, updated_at,
                asset, internal_system_number, calloff_po_id, currency
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                calloff_sc_id, "SC-CO-RESOLVE", USER["user_id"], "call_off",
                1000, 30000, "2026-01-01", "2026-12-31",
                "pending", "Test call-off", USER["user_id"], ts, ts,
                "N", "7600-RESOLVE-TEST", None, "CNY",
            ),
        )
        conn.commit()

    # 3. Verify calloff_po_id is initially NULL
    with connect(app_config) as conn:
        row = conn.execute(
            "SELECT calloff_po_id FROM sc_records WHERE sc_id = ?",
            (calloff_sc_id,),
        ).fetchone()
        assert row["calloff_po_id"] is None

    # 4. Run post-import UPDATE (same SQL as Task 8 Step 5)
    with connect(app_config) as conn:
        updated = conn.execute(
            """UPDATE sc_records
               SET calloff_po_id = (
                 SELECT po_id FROM pos
                 WHERE pos.po_no = sc_records.internal_system_number
                   AND pos.po_no IS NOT NULL AND pos.po_no != ''
                 ORDER BY pos.created_at DESC
                 LIMIT 1
               )
               WHERE request_type = 'call_off'
                 AND (calloff_po_id IS NULL OR calloff_po_id = '')
                 AND internal_system_number IS NOT NULL
                 AND internal_system_number != ''"""
        ).rowcount
        conn.commit()
    assert updated >= 1

    # 5. Verify calloff_po_id is now resolved
    with connect(app_config) as conn:
        row = conn.execute(
            "SELECT calloff_po_id FROM sc_records WHERE sc_id = ?",
            (calloff_sc_id,),
        ).fetchone()
        assert row["calloff_po_id"] == po_fc["po_id"]

    # 6. Verify budget includes the resolved call-off
    fc_budget = compute_po_fc_budget(app_config, po_fc["po_id"])
    assert fc_budget["allocated_calloff_amount"] == 30000.0
