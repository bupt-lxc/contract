# tests/test_export_service.py
import pytest
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services import export_service


def test_build_cascade_rows_sc_only(app_config):
    """SC-only export returns flat SC rows with _type='SC' and no children."""
    migrate(app_config)

    # Seed users
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-001', 'SC-2026-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Test SC', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-002', 'SC-2026-002', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'draft', 'Draft SC', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    current_user = {"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"}
    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user=current_user,
    )

    assert len(rows) == 1  # draft SC invisible to admin who is not requester
    assert rows[0]["_type"] == "SC"
    assert rows[0]["sc_id"] == "sc-001"
    assert rows[0]["sc_no"] == "SC-2026-001"
    assert rows[0]["sc_amount"] == 50000


def test_build_cascade_rows_sc_po(app_config):
    """SC+PO cascade returns SC rows followed by their PO children."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at) VALUES ('sc-001', 'SC-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('v1', 'Vendor A', 'Parts', 'U1', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO pos (po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status, created_at, updated_at) VALUES ('po-001', 'sc-001', 'v1', 'PO-001', 'U2', 20000, 'active', '2026-01-20', '2026-01-20')")
    conn.execute("INSERT INTO pos (po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status, created_at, updated_at) VALUES ('po-002', 'sc-001', 'v1', 'PO-002', 'U2', 10000, 'draft', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    current_user = {"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"}
    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": True, "gr": False},
        current_user=current_user,
    )

    types = [r["_type"] for r in rows]
    assert types == ["SC", "PO", "PO"]
    assert rows[0]["sc_id"] == "sc-001"
    assert rows[1]["_type"] == "PO"
    assert rows[1]["po_no"] == "PO-001"
    assert rows[1]["sc_no"] == "SC-001"  # parent context carried
    assert rows[2]["po_no"] == "PO-002"


def test_build_cascade_rows_sc_po_gr(app_config):
    """SC+PO+GR cascade returns full hierarchy."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at) VALUES ('sc-001', 'SC-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('v1', 'Vendor A', 'Parts', 'U1', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO pos (po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status, created_at, updated_at) VALUES ('po-001', 'sc-001', 'v1', 'PO-001', 'U2', 20000, 'active', '2026-01-20', '2026-01-20')")
    conn.execute("INSERT INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at) VALUES ('gr-001', 'GR-001', 'po-001', 'U2', 5000, 4800, 'approved', 'U2', '2026-02-01')")
    conn.execute("INSERT INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at) VALUES ('gr-002', 'GR-002', 'po-001', 'U2', 3000, 3000, 'pending', 'U2', '2026-02-15')")
    conn.commit()
    conn.close()

    current_user = {"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"}
    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": True, "gr": True},
        current_user=current_user,
    )

    types = [r["_type"] for r in rows]
    assert types == ["SC", "PO", "GR", "GR"]


def test_build_cascade_rows_po_gr(app_config):
    """PO+GR cascade from PO root."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at) VALUES ('sc-001', 'SC-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('v1', 'Vendor A', 'Parts', 'U1', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO pos (po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status, created_at, updated_at) VALUES ('po-001', 'sc-001', 'v1', 'PO-001', 'U2', 20000, 'active', '2026-01-20', '2026-01-20')")
    conn.execute("INSERT INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at) VALUES ('gr-001', 'GR-001', 'po-001', 'U2', 5000, 4800, 'approved', 'U2', '2026-02-01')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "po", {}, "created_at", "desc",
        cascade_options={"gr": True},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
    )

    types = [r["_type"] for r in rows]
    assert types == ["PO", "GR"]
    assert rows[0]["po_no"] == "PO-001"
    assert rows[0]["sc_no"] == "SC-001"
    assert rows[1]["gr_no"] == "GR-001"


def test_build_cascade_rows_selected_ids(app_config):
    """selected_ids takes priority over filters."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at) VALUES ('sc-001', 'SC-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at) VALUES ('sc-002', 'SC-002', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    current_user = {"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"}
    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user=current_user,
        selected_ids=["sc-001"],
    )

    assert len(rows) == 1
    assert rows[0]["sc_id"] == "sc-001"


def test_compute_statistics_sc_only(app_config):
    """Statistics for SC-only export includes overview, financial, budget_health, processing, by_requester."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, created_by, created_at, updated_at, submitted_date, pending_date, approved_date, finished_at) VALUES ('sc-001', 'SC-001', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'U2', '2026-01-15', '2026-01-20', '2026-01-15', '2026-01-20', '2026-01-25', null)")
    conn.commit()
    conn.close()

    stats = export_service.compute_statistics(app_config, {"SC"}, {})

    assert "overview" in stats
    assert "financial" in stats
    assert "budget_health" in stats  # SC present
    assert "processing" in stats
    assert "by_requester" in stats

    overview = stats["overview"]
    assert overview["sc"]["total_count"] == 1
    assert overview["sc"]["total_amount"] == 50000
    assert overview["sc"]["approved_count"] == 1

    financial = stats["financial"]
    assert len(financial) >= 1
    assert financial[0]["sc_amount"] == 50000

    budget = stats["budget_health"]
    assert len(budget) == 1
    assert budget[0]["sc_no"] == "SC-001"


def test_compute_statistics_no_budget_health_without_sc(app_config):
    """budget_health sheet is absent when SC is not in entity_types."""
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.commit()
    conn.close()

    stats = export_service.compute_statistics(app_config, {"PO"}, {})
    assert "budget_health" not in stats
    assert "overview" in stats


def test_cascade_export_honors_text_search_for_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )

    assert [row["sc_no"] for row in rows] == ["SC-ALPHA"]


def test_export_statistics_use_same_text_criteria_as_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": False, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )
    stats = export_service.compute_statistics(
        app_config,
        {"SC"},
        {},
        export_rows=rows,
        text="alpha",
    )

    assert stats["overview"]["sc"]["total_count"] == 1
    assert stats["overview"]["sc"]["total_amount"] == 50000


def test_cascade_statistics_are_based_on_exported_child_rows(app_config):
    migrate(app_config)
    import sqlite3
    conn = sqlite3.connect(app_config.db_path)
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U1', 'M001', 'Alice', 'admin', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) VALUES ('U2', 'M002', 'Bob', 'requester', 'active', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('VAlpha', 'Alpha Vendor', 'Parts', 'U1', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) VALUES ('VBeta', 'Beta Vendor', 'Parts', 'U1', '2026-01-01', '2026-01-01')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-alpha', 'SC-ALPHA', 'U2', 'new', 1000, 50000, 'CNY', '2026-01-01', '2026-06-30', 'approved', 'Alpha service', 'U2', '2026-01-15', '2026-01-15')")
    conn.execute("INSERT INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, currency, service_period_start, service_period_end, status, description, created_by, created_at, updated_at) VALUES ('sc-beta', 'SC-BETA', 'U2', 'new', 2000, 30000, 'CNY', '2026-02-01', '2026-07-31', 'approved', 'Beta service', 'U2', '2026-02-01', '2026-02-01')")
    conn.execute("INSERT INTO pos (po_id, po_no, sc_id, vendor_id, po_amount, status, created_at, updated_at) VALUES ('po-alpha', 'PO-ALPHA', 'sc-alpha', 'VAlpha', 700, 'active', '2026-01-20', '2026-01-20')")
    conn.execute("INSERT INTO pos (po_id, po_no, sc_id, vendor_id, po_amount, status, created_at, updated_at) VALUES ('po-beta', 'PO-BETA', 'sc-beta', 'VBeta', 900, 'active', '2026-02-10', '2026-02-10')")
    conn.commit()
    conn.close()

    rows = export_service.build_cascade_rows(
        app_config, "sc", {}, "created_at", "desc",
        cascade_options={"po": True, "gr": False},
        current_user={"user_id": "U1", "machine_id": "M001", "user_name": "Alice", "role": "admin"},
        text="alpha",
    )
    stats = export_service.compute_statistics(app_config, {"SC", "PO"}, {}, export_rows=rows)

    assert stats["overview"]["sc"]["total_count"] == 1
    assert stats["overview"]["po"]["total_count"] == 1
    assert stats["overview"]["po"]["total_amount"] == 700
