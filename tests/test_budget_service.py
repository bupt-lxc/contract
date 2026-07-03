import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.services.budget_service import (
    compute_po_budget,
    compute_po_budget_decimal,
    compute_po_fc_budget,
    compute_sc_budget,
    compute_sc_budget_decimal,
    compute_sc_fc_budget,
)


TIMESTAMP = "2026-05-19T00:00:00+00:00"


def seed_user(conn):
    conn.execute(
        """
        insert into users (
          user_id,
          machine_id,
          user_name,
          role,
          email,
          status,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "U1",
            "machine1",
            "Requester",
            "requester",
            None,
            "active",
            TIMESTAMP,
            TIMESTAMP,
        ),
    )


def seed_sc(conn, sc_id="SC1", sc_amount=1000):
    conn.execute(
        """
        insert into sc_records (
          sc_id,
          sc_no,
          requester_id,
          request_type,
          cost_center,
          sc_amount,
          service_period_start,
          service_period_end,
          status,
          description,
          created_by,
          created_at,
          updated_at,
          approved_by,
          approved_at,
          finished_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            sc_id,
            f"{sc_id}-NO",
            "U1",
            "service",
            100,
            sc_amount,
            "2026-05-01",
            "2026-05-31",
            "approved",
            None,
            "U1",
            TIMESTAMP,
            TIMESTAMP,
            "U1",
            TIMESTAMP,
            None,
        ),
    )


def seed_vendor(conn):
    conn.execute(
        """
        insert into vendors (
          vendor_id,
          vendor_name,
          ksrm_vendor_code,
          contact_person,
          phone,
          service_scope,
          email,
          description,
          inquiry_history,
          created_by,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "V1",
            "Vendor",
            None,
            None,
            None,
            "General Service",
            None,
            None,
            None,
            "U1",
            TIMESTAMP,
            TIMESTAMP,
        ),
    )


def seed_po(conn, po_id="PO1", sc_id="SC1", po_amount=800):
    conn.execute(
        """
        insert into pos (
          po_id,
          sc_id,
          vendor_id,
          po_no,
          po_amount,
          status,
          contract_from,
          contract_to,
          contract_no,
          payment_frequency,
          created_at,
          updated_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            po_id,
            sc_id,
            "V1",
            f"{po_id}-NO",
            po_amount,
            "active",
            None,
            None,
            None,
            None,
            TIMESTAMP,
            TIMESTAMP,
        ),
    )


def seed_gr(
    conn,
    gr_id,
    po_id="PO1",
    estimated_amount=100,
    con_value=None,
    status="pending",
):
    conn.execute(
        """
        insert into gr_requests (
          gr_id,
          gr_no,
          po_id,
          requester_id,
          estimated_amount,
          con_value,
          status,
          remark,
          created_by,
          created_at,
          approved_by,
          approved_at,
          denied_by,
          denied_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            gr_id,
            None,
            po_id,
            "U1",
            estimated_amount,
            con_value,
            status,
            None,
            "U1",
            TIMESTAMP,
            "U1" if status == "approved" else None,
            TIMESTAMP if status == "approved" else None,
            "U1" if status == "denied" else None,
            TIMESTAMP if status == "denied" else None,
        ),
    )


def seed_base_budget_records(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn)
        seed_vendor(conn)
        seed_po(conn)
        seed_gr(conn, "GR1", estimated_amount=100, status="pending")
        seed_gr(
            conn,
            "GR2",
            estimated_amount=150,
            con_value=150,
            status="approved",
        )
        conn.commit()


def seed_sc_without_pos(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn)
        conn.commit()


def seed_po_without_grs(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn)
        seed_vendor(conn)
        seed_po(conn)
        conn.commit()


def test_compute_sc_budget_sums_pending_approved_and_po_allocation(app_config):
    seed_base_budget_records(app_config)

    budget = compute_sc_budget(app_config, "SC1")

    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 100.0,
        "sc_con_value_total": 150.0,
        "sc_pending_total_incl_tax": 100.0,
        "sc_available_amount": 750.0,
        "allocated_po_amount": 800.0,
        "unallocated_sc_amount": 200.0,
    }


def test_compute_po_budget_derives_open_po_amount(app_config):
    seed_base_budget_records(app_config)

    budget = compute_po_budget(app_config, "PO1")

    assert budget == {
        "po_amount": 800.0,
        "po_pending_total": 100.0,
        "po_con_value_total": 150.0,
        "po_pending_total_incl_tax": 100.0,
        "open_po_amount": 550.0,
    }


def test_compute_sc_budget_raises_not_found_for_unknown_sc(app_config):
    migrate(app_config)

    with pytest.raises(NotFound, match="SC not found: missing"):
        compute_sc_budget(app_config, "missing")


def test_compute_po_budget_raises_not_found_for_unknown_po(app_config):
    migrate(app_config)

    with pytest.raises(NotFound, match="PO not found: missing"):
        compute_po_budget(app_config, "missing")


def test_po_budget_open_po_amount_is_returned_only_as_derived_key(app_config):
    seed_base_budget_records(app_config)

    with connect(app_config) as conn:
        po_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(pos)")
        }
        gr_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(gr_requests)")
        }

    assert "open_po_amount" not in po_columns
    assert "open_po_amount" not in gr_columns
    assert compute_po_budget(app_config, "PO1")["open_po_amount"] == 550.0


def test_denied_grs_are_excluded_from_sc_and_po_budget(app_config):
    seed_base_budget_records(app_config)
    with connect(app_config) as conn:
        seed_gr(
            conn,
            "GR3",
            estimated_amount=300,
            con_value=300,
            status="denied",
        )
        conn.commit()

    assert compute_sc_budget(app_config, "SC1")["sc_available_amount"] == 750.0
    assert compute_po_budget(app_config, "PO1")["open_po_amount"] == 550.0


def test_compute_sc_budget_rejects_approved_gr_with_null_con_value(app_config):
    seed_base_budget_records(app_config)
    with connect(app_config) as conn:
        seed_gr(conn, "GR3", estimated_amount=300, status="approved")
        conn.commit()

    with pytest.raises(
        ConflictError,
        match="Approved GR has NULL con_value for SC SC1",
    ):
        compute_sc_budget(app_config, "SC1")


def test_compute_po_budget_rejects_approved_gr_with_null_con_value(app_config):
    seed_base_budget_records(app_config)
    with connect(app_config) as conn:
        seed_gr(conn, "GR3", estimated_amount=300, status="approved")
        conn.commit()

    with pytest.raises(
        ConflictError,
        match="Approved GR has NULL con_value for PO PO1",
    ):
        compute_po_budget(app_config, "PO1")


def test_compute_sc_budget_returns_zero_totals_when_sc_has_no_pos(app_config):
    seed_sc_without_pos(app_config)

    budget = compute_sc_budget(app_config, "SC1")

    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 0.0,
        "sc_con_value_total": 0.0,
        "sc_pending_total_incl_tax": 0.0,
        "sc_available_amount": 1000.0,
        "allocated_po_amount": 0.0,
        "unallocated_sc_amount": 1000.0,
    }


def test_compute_po_budget_returns_zero_totals_when_po_has_no_grs(app_config):
    seed_po_without_grs(app_config)

    budget = compute_po_budget(app_config, "PO1")

    assert budget == {
        "po_amount": 800.0,
        "po_pending_total": 0.0,
        "po_con_value_total": 0.0,
        "po_pending_total_incl_tax": 0.0,
        "open_po_amount": 800.0,
    }


def test_compute_sc_budget_counts_grs_once_across_multiple_pos(app_config):
    seed_base_budget_records(app_config)
    with connect(app_config) as conn:
        seed_po(conn, po_id="PO2", po_amount=200)
        seed_gr(
            conn,
            "GR3",
            po_id="PO2",
            estimated_amount=50,
            status="pending",
        )
        seed_gr(
            conn,
            "GR4",
            po_id="PO2",
            estimated_amount=75,
            con_value=75,
            status="approved",
        )
        conn.commit()

    budget = compute_sc_budget(app_config, "SC1")

    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 150.0,
        "sc_con_value_total": 225.0,
        "sc_pending_total_incl_tax": 150.0,
        "sc_available_amount": 625.0,
        "allocated_po_amount": 1000.0,
        "unallocated_sc_amount": 0.0,
    }


def test_decimal_sc_budget_uses_exact_decimal_arithmetic(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount="0.3")
        seed_vendor(conn)
        seed_po(conn, po_amount="0.3")
        seed_gr(conn, "GR1", estimated_amount="0.1", status="pending")
        seed_gr(
            conn,
            "GR2",
            estimated_amount="0.2",
            con_value="0.2",
            status="approved",
        )
        conn.commit()

    decimal_budget = compute_sc_budget_decimal(app_config, "SC1")
    float_budget = compute_sc_budget(app_config, "SC1")

    assert decimal_budget["sc_available_amount"] == 0
    assert decimal_budget["unallocated_sc_amount"] == 0
    assert float_budget["sc_available_amount"] == 0.0


def test_decimal_po_budget_uses_exact_decimal_arithmetic(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount="0.3")
        seed_vendor(conn)
        seed_po(conn, po_amount="0.3")
        seed_gr(conn, "GR1", estimated_amount="0.1", status="pending")
        seed_gr(
            conn,
            "GR2",
            estimated_amount="0.2",
            con_value="0.2",
            status="approved",
        )
        conn.commit()

    decimal_budget = compute_po_budget_decimal(app_config, "PO1")
    float_budget = compute_po_budget(app_config, "PO1")

    assert decimal_budget["open_po_amount"] == 0
    assert float_budget["open_po_amount"] == 0.0


def test_po_pending_total_incl_tax_applies_tax_rate(app_config):
    """pending_total_incl_tax = estimated_amount * (1 + tax_rate/100)"""
    from sc_gr_app.db.connection import connect
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_amount=1000)
        seed_vendor(conn)
        seed_po(conn, po_amount=500)
        # GR with 13% tax (gross_cost = 100 * 1.13 = 113)
        conn.execute(
            """
            insert into gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value,
              gross_cost, tax_rate, status, created_by, created_at
            ) values ('GR1', 'PO1', 'U1', 100, NULL, 113, 13, 'pending', 'U1', ?)
            """,
            (TIMESTAMP,),
        )
        # GR with no tax (gross_cost = estimated_amount = 200)
        conn.execute(
            """
            insert into gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value,
              gross_cost, tax_rate, status, created_by, created_at
            ) values ('GR2', 'PO1', 'U1', 200, NULL, 200, NULL, 'manager_confirm', 'U1', ?)
            """,
            (TIMESTAMP,),
        )
        conn.commit()

    budget = compute_po_budget(app_config, "PO1")

    assert budget["po_pending_total"] == 300.0              # 100 + 200
    assert budget["po_pending_total_incl_tax"] == 313.0     # 100*1.13 + 200*1.0
    assert budget["po_con_value_total"] == 0.0


# ---------------------------------------------------------------------------
# Framework Contract (FC) budget tests
# ---------------------------------------------------------------------------


def _seed_fc_chain(app_config):
    """Create test data: SC(FC) + PO(FC) using direct SQL inserts.

    Bypasses service-layer functions that may not yet support calloff_po_id
    (Task 3). Inserts directly via SQL.

    Returns (sc_fc_id, po_fc_id).
    """
    migrate(app_config)
    with connect(app_config) as conn:
        conn.execute(
            """
            INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("U-FC", "M-FC", "FC Tester", "requester", None, "active", TIMESTAMP, TIMESTAMP),
        )
        conn.execute(
            """
            INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("V-FC", "FC Vendor", "Others", "U-FC", TIMESTAMP, TIMESTAMP),
        )
        sc_fc_id = "SC-FC-001"
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status,
              created_by, created_at, updated_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (sc_fc_id, f"{sc_fc_id}-NO", "U-FC", "FC", 1000, 100000.0,
             "2026-01-01", "2026-12-31", "approved",
             "U-FC", TIMESTAMP, TIMESTAMP, "U-FC", TIMESTAMP),
        )
        po_fc_id = "PO-FC-001"
        conn.execute(
            """
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (po_fc_id, sc_fc_id, "V-FC", f"{po_fc_id}-NO", 80000.0, "active",
             TIMESTAMP, TIMESTAMP),
        )
        conn.commit()
    return sc_fc_id, po_fc_id


def test_compute_po_fc_budget_no_calloffs(app_config):
    """FC PO with no call-off SCs: open = full PO amount."""
    sc_id, po_id = _seed_fc_chain(app_config)

    budget = compute_po_fc_budget(app_config, po_id)
    assert budget["po_amount"] == 80000.0
    assert budget["allocated_calloff_amount"] == 0.0
    assert budget["pending_calloff_amount"] == 0.0
    assert budget["open_po_amount"] == 80000.0
    assert budget["downstream_consumed"] == 0.0
    assert budget["downstream_pending_gr"] == 0.0
    assert budget["downstream_pending_gr_tax"] == 0.0


def test_compute_po_fc_budget_with_calloffs(app_config):
    """FC PO with call-off SCs: open reflects allocated call-off amount."""
    sc_id, po_id = _seed_fc_chain(app_config)

    with connect(app_config) as conn:
        # Insert 2 call-off SCs with different statuses
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-001", "SC-CO-001-NO", "U-FC", "material", 2000, 30000.0,
             "2026-01-01", "2026-12-31", "approved", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP),
        )
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-002", "SC-CO-002-NO", "U-FC", "service", 3000, 20000.0,
             "2026-01-01", "2026-12-31", "pending", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP),
        )
        conn.commit()

    budget = compute_po_fc_budget(app_config, po_id)
    assert budget["allocated_calloff_amount"] == 50000.0   # 30000 + 20000
    assert budget["pending_calloff_amount"] == 50000.0     # both approved & pending count
    assert budget["open_po_amount"] == 30000.0             # 80000 - 50000


def test_compute_po_fc_budget_rejects_non_fc_po(app_config):
    """Calling FC budget on a regular (non-FC) PO raises ValidationError."""
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_id="SC-REG", sc_amount=50000)
        seed_vendor(conn)
        seed_po(conn, po_id="PO-REG", sc_id="SC-REG", po_amount=30000)
        conn.commit()

    with pytest.raises(ValidationError, match="not under an FC-type SC"):
        compute_po_fc_budget(app_config, "PO-REG")


def test_compute_sc_fc_budget(app_config):
    """SC(FC) budget: full downstream trace with PO allocation."""
    sc_id, po_id = _seed_fc_chain(app_config)

    budget = compute_sc_fc_budget(app_config, sc_id)
    assert budget["sc_amount"] == 100000.0
    assert budget["allocated_po_amount"] == 80000.0
    assert budget["unallocated_sc_amount"] == 20000.0
    assert budget["downstream_calloff_amount"] == 0.0
    assert budget["pending_calloff_amount"] == 0.0
    assert budget["downstream_consumed"] == 0.0
    assert budget["downstream_pending_gr"] == 0.0
    assert budget["downstream_pending_gr_tax"] == 0.0


def test_compute_po_fc_budget_downstream_gr_trace(app_config):
    """FC PO budget traces downstream GRs through call-off SCs -> POs -> GRs."""
    sc_id, po_id = _seed_fc_chain(app_config)

    with connect(app_config) as conn:
        # Create call-off SC
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-001", "SC-CO-001-NO", "U-FC", "material", 2000, 30000.0,
             "2026-01-01", "2026-12-31", "approved", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP, "U-FC", TIMESTAMP),
        )
        # Create PO under call-off SC
        conn.execute(
            """
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PO-CO-001", "SC-CO-001", "V-FC", "PO-CO-001-NO", 20000.0, "active",
             TIMESTAMP, TIMESTAMP),
        )
        # Create GRs under that PO
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status,
              created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-001", "PO-CO-001", "U-FC", 5000.0, None, "pending",
             "U-FC", TIMESTAMP),
        )
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status,
              created_by, created_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-002", "PO-CO-001", "U-FC", 8000.0, 8000.0, "approved",
             "U-FC", TIMESTAMP, "U-FC", TIMESTAMP),
        )
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, gross_cost, status,
              created_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-003", "PO-CO-001", "U-FC", 3000.0, 3390.0, "manager_confirm",
             "U-FC", TIMESTAMP),
        )
        conn.commit()

    budget = compute_po_fc_budget(app_config, po_id)
    assert budget["allocated_calloff_amount"] == 30000.0
    assert budget["open_po_amount"] == 50000.0        # 80000 - 30000
    assert budget["downstream_consumed"] == 8000.0     # approved GR con_value
    assert budget["downstream_pending_gr"] == 8000.0   # 5000 (pending) + 3000 (manager_confirm)
    assert budget["downstream_pending_gr_tax"] == 8390.0  # 5000*1.0 + 3390 (gross_cost)


def test_compute_sc_fc_budget_downstream_gr_trace(app_config):
    """SC(FC) budget traces downstream GRs through full 5-tier chain."""
    sc_id, po_id = _seed_fc_chain(app_config)

    with connect(app_config) as conn:
        # Create call-off SC
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-001", "SC-CO-001-NO", "U-FC", "material", 2000, 30000.0,
             "2026-01-01", "2026-12-31", "approved", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP, "U-FC", TIMESTAMP),
        )
        # Create PO under call-off SC
        conn.execute(
            """
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PO-CO-001", "SC-CO-001", "V-FC", "PO-CO-001-NO", 20000.0, "active",
             TIMESTAMP, TIMESTAMP),
        )
        # Create approved GR with con_value
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status,
              created_by, created_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-001", "PO-CO-001", "U-FC", 10000.0, 10000.0, "approved",
             "U-FC", TIMESTAMP, "U-FC", TIMESTAMP),
        )
        conn.commit()

    budget = compute_sc_fc_budget(app_config, sc_id)
    assert budget["sc_amount"] == 100000.0
    assert budget["allocated_po_amount"] == 80000.0
    assert budget["unallocated_sc_amount"] == 20000.0
    assert budget["downstream_calloff_amount"] == 30000.0
    assert budget["pending_calloff_amount"] == 30000.0    # approved call-off SC
    assert budget["downstream_consumed"] == 10000.0
    assert budget["downstream_pending_gr"] == 0.0
    assert budget["downstream_pending_gr_tax"] == 0.0


def test_compute_po_fc_budget_not_found(app_config):
    """Non-existent PO raises NotFound."""
    migrate(app_config)

    with pytest.raises(NotFound, match="PO not found: missing"):
        compute_po_fc_budget(app_config, "missing")


def test_compute_sc_fc_budget_rejects_non_fc_sc(app_config):
    """Calling FC SC budget on a regular SC raises ValidationError."""
    migrate(app_config)
    with connect(app_config) as conn:
        seed_user(conn)
        seed_sc(conn, sc_id="SC-REG", sc_amount=50000)
        conn.commit()

    with pytest.raises(ValidationError, match="not an FC-type SC"):
        compute_sc_fc_budget(app_config, "SC-REG")


def test_compute_sc_fc_budget_not_found(app_config):
    """Non-existent SC raises NotFound."""
    migrate(app_config)

    with pytest.raises(NotFound, match="SC not found: missing"):
        compute_sc_fc_budget(app_config, "missing")


def test_compute_po_fc_budget_rejects_null_con_value_downstream(app_config):
    """Approved downstream GR with NULL con_value raises ConflictError."""
    sc_id, po_id = _seed_fc_chain(app_config)

    with connect(app_config) as conn:
        # Create call-off SC
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-001", "SC-CO-001-NO", "U-FC", "material", 2000, 30000.0,
             "2026-01-01", "2026-12-31", "approved", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP, "U-FC", TIMESTAMP),
        )
        # Create PO under call-off SC
        conn.execute(
            """
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PO-CO-001", "SC-CO-001", "V-FC", "PO-CO-001-NO", 20000.0, "active",
             TIMESTAMP, TIMESTAMP),
        )
        # Approved GR with NULL con_value
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status,
              created_by, created_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-001", "PO-CO-001", "U-FC", 10000.0, None, "approved",
             "U-FC", TIMESTAMP, "U-FC", TIMESTAMP),
        )
        conn.commit()

    with pytest.raises(ConflictError, match="NULL con_value"):
        compute_po_fc_budget(app_config, po_id)


def test_compute_sc_fc_budget_rejects_null_con_value_downstream(app_config):
    """Approved downstream GR with NULL con_value raises ConflictError for FC SC."""
    sc_id, po_id = _seed_fc_chain(app_config)

    with connect(app_config) as conn:
        # Create call-off SC
        conn.execute(
            """
            INSERT INTO sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, calloff_po_id,
              created_by, created_at, updated_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("SC-CO-001", "SC-CO-001-NO", "U-FC", "material", 2000, 30000.0,
             "2026-01-01", "2026-12-31", "approved", po_id,
             "U-FC", TIMESTAMP, TIMESTAMP, "U-FC", TIMESTAMP),
        )
        # Create PO under call-off SC
        conn.execute(
            """
            INSERT INTO pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("PO-CO-001", "SC-CO-001", "V-FC", "PO-CO-001-NO", 20000.0, "active",
             TIMESTAMP, TIMESTAMP),
        )
        # Approved GR with NULL con_value
        conn.execute(
            """
            INSERT INTO gr_requests (
              gr_id, po_id, requester_id, estimated_amount, con_value, status,
              created_by, created_at, approved_by, approved_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("GR-CO-001", "PO-CO-001", "U-FC", 10000.0, None, "approved",
             "U-FC", TIMESTAMP, "U-FC", TIMESTAMP),
        )
        conn.commit()

    with pytest.raises(ConflictError, match="NULL con_value"):
        compute_sc_fc_budget(app_config, sc_id)
