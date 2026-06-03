from datetime import datetime, timezone

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.sc_service import _generate_sc_id
from sc_gr_app.services.po_service import _generate_po_id
from sc_gr_app.services.gr_service import _generate_gr_id


def _seed_user(app_config, user_id="U-001", machine_id="M1", user_name="u1", role="requester"):
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, NULL, 'active', ?, ?)",
            (user_id, machine_id, user_name, role, timestamp, timestamp),
        )
        conn.commit()


def test_generate_sc_id_creates_sequential_ids(app_config):
    migrate(app_config)
    mid = "TESTUSR"
    _seed_user(app_config, user_id="U-001")

    id1 = _generate_sc_id(app_config, mid)
    # Manually insert to simulate prior record
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, sc_amount, status, created_by, created_at, updated_at) "
            "VALUES (?, ?, 100, 'draft', 'U-001', ?, ?)",
            (id1, "U-001", timestamp, timestamp),
        )
        conn.commit()
    id2 = _generate_sc_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"SC-{mid}-")


def test_generate_po_id_creates_sequential_ids(app_config):
    migrate(app_config)
    mid = "TESTUSR"
    _seed_user(app_config, user_id="U-001")
    timestamp = datetime.now(timezone.utc).isoformat()

    id1 = _generate_po_id(app_config, mid)
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, request_type, cost_center, sc_amount, "
            "service_period_start, service_period_end, status, created_by, created_at, updated_at) "
            "VALUES ('SC-001', 'U-001', 'service', 1001, 100, "
            "'2026-01-01', '2026-12-31', 'approved', 'U-001', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
            "VALUES ('V-001', 'Test Vendor', 'General Service', 'U-001', ?, ?)",
            (timestamp, timestamp),
        )
        conn.commit()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO pos (po_id, sc_id, vendor_id, po_amount, status, created_at, updated_at) "
            "VALUES (?, 'SC-001', 'V-001', 100, 'activing', ?, ?)",
            (id1, timestamp, timestamp),
        )
        conn.commit()
    id2 = _generate_po_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"PO-{mid}-")


def test_generate_gr_id_creates_sequential_ids(app_config):
    migrate(app_config)
    mid = "TESTUSR"
    _seed_user(app_config, user_id="U-001")
    timestamp = datetime.now(timezone.utc).isoformat()

    id1 = _generate_gr_id(app_config, mid)
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, request_type, cost_center, sc_amount, "
            "service_period_start, service_period_end, status, created_by, created_at, updated_at) "
            "VALUES ('SC-GR', 'U-001', 'service', 1001, 100, "
            "'2026-01-01', '2026-12-31', 'approved', 'U-001', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
            "VALUES ('V-001', 'Test Vendor', 'General Service', 'U-001', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO pos (po_id, sc_id, vendor_id, po_amount, status, created_at, updated_at) "
            "VALUES ('PO-GR', 'SC-GR', 'V-001', 100, 'activing', ?, ?)",
            (timestamp, timestamp),
        )
        conn.commit()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, status, created_by, created_at) "
            "VALUES (?, ?, 'PO-GR', 'U-001', 50, 'pending', 'U-001', ?)",
            (id1, None, timestamp),
        )
        conn.commit()
    id2 = _generate_gr_id(app_config, mid)
    assert id2.endswith("-002")
    assert id2.startswith(f"GR-{mid}-")
