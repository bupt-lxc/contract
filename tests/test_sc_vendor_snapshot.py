import json

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.sc_service import create_sc_draft, get_sc_detail, submit_sc, update_sc
from sc_gr_app.services.vendor_service import create_vendor, update_vendor

USER = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
ADMIN = {"user_id": "A1", "role": "admin", "machine_id": "M2"}


def seed_users(app_config):
    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "U1", "M1", "Requester", "requester", None, "active",
                "2026-05-19T00:00:00+00:00", "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "A1", "M2", "Admin", "admin", None, "active",
                "2026-05-19T00:00:00+00:00", "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_sc_draft_saves_vendor_snapshot(app_config):
    """When SC draft is created with vendor_ids, snapshot is stored in sc_vendors."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Original Name",
        "company_name_cn": "原始名称有限公司",
        "service_scope": "General Service",
        "contact_person": "Alice",
        "phone": "123456",
        "email": "a@b.com",
    })
    sc = create_sc_draft(app_config, USER, {
        "requester_id": "U1",
        "vendor_ids": ["V1"],
    })
    with connect(app_config) as conn:
        row = conn.execute(
            "SELECT vendor_snapshot FROM sc_vendors WHERE sc_id = ?",
            (sc["sc_id"],),
        ).fetchone()
    assert row["vendor_snapshot"] is not None
    snapshot = json.loads(row["vendor_snapshot"])
    assert snapshot["vendor_name"] == "Original Name"
    assert snapshot["company_name_cn"] == "原始名称有限公司"
    assert snapshot["contact_person"] == "Alice"
    assert snapshot["phone"] == "123456"


def test_vendor_snapshot_preserved_when_vendor_updated(app_config):
    """Changing vendor info does NOT affect existing SC snapshots."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Original Name",
        "service_scope": "General Service",
    })
    sc = create_sc_draft(app_config, USER, {
        "requester_id": "U1",
        "vendor_ids": ["V1"],
    })
    # Update the vendor's live record
    update_vendor(app_config, USER, "V1", {"vendor_name": "Changed Name"})
    # SC detail should still show original snapshot
    detail = get_sc_detail(app_config, ADMIN, sc["sc_id"])
    assert len(detail["vendors"]) == 1
    assert detail["vendors"][0]["vendor_name"] == "Original Name"


def test_vendor_snapshot_updated_on_sc_edit(app_config):
    """Re-assigning vendors updates the snapshot to current vendor data."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Vendor One",
        "service_scope": "General Service",
    })
    create_vendor(app_config, USER, {
        "vendor_id": "V2",
        "vendor_name": "Vendor Two",
        "service_scope": "General Service",
    })
    sc = create_sc_draft(app_config, USER, {
        "requester_id": "U1",
        "vendor_ids": ["V1"],
    })
    # Change vendor to V2
    update_sc(app_config, USER, sc["sc_id"], {"vendor_ids": ["V2"]})
    detail = get_sc_detail(app_config, ADMIN, sc["sc_id"])
    assert len(detail["vendors"]) == 1
    assert detail["vendors"][0]["vendor_name"] == "Vendor Two"


def test_vendor_snapshot_null_falls_back_to_live_vendor(app_config):
    """SC records without snapshots (pre-migration) use live vendor data."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Live Vendor",
        "company_name_cn": "实时供应商有限公司",
        "service_scope": "General Service",
        "contact_person": "Bob",
    })
    sc = create_sc_draft(app_config, USER, {
        "requester_id": "U1",
        "vendor_ids": ["V1"],
    })
    # Simulate pre-migration state: null out the snapshot
    with connect(app_config) as conn:
        conn.execute(
            "UPDATE sc_vendors SET vendor_snapshot = NULL WHERE sc_id = ?",
            (sc["sc_id"],),
        )
        conn.commit()
    detail = get_sc_detail(app_config, ADMIN, sc["sc_id"])
    assert len(detail["vendors"]) == 1
    assert detail["vendors"][0]["vendor_name"] == "Live Vendor"
    assert detail["vendors"][0]["company_name_cn"] == "实时供应商有限公司"
    assert detail["vendors"][0]["contact_person"] == "Bob"


def test_vendor_snapshot_on_submit(app_config):
    """Submitting an SC also captures vendor snapshots."""
    migrate(app_config)
    seed_users(app_config)
    create_vendor(app_config, USER, {
        "vendor_id": "V1",
        "vendor_name": "Submit Vendor",
        "service_scope": "General Service",
    })
    sc = create_sc_draft(app_config, USER, {"requester_id": "U1"})
    sc_id = sc["sc_id"]
    submit_sc(app_config, USER, sc_id, {
        "sc_no": "SC-TEST",
        "request_type": "service",
        "cost_center": 1001,
        "sc_amount": 5000,
        "service_period_start": "2026-01-01",
        "service_period_end": "2026-12-31",
        "vendor_ids": ["V1"],
    })
    with connect(app_config) as conn:
        row = conn.execute(
            "SELECT vendor_snapshot FROM sc_vendors WHERE sc_id = ?",
            (sc_id,),
        ).fetchone()
    assert row is not None
    snapshot = json.loads(row["vendor_snapshot"])
    assert snapshot["vendor_name"] == "Submit Vendor"
