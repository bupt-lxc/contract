import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import NotFound
from sc_gr_app.services.budget_service import compute_po_budget, compute_sc_budget


TIMESTAMP = "2026-05-19T00:00:00+00:00"


def seed_budget_records(app_config):
    migrate(app_config)
    with connect(app_config) as conn:
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
              closed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SC1",
                "SC-001",
                "U1",
                "service",
                100,
                1000,
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
                "PO1",
                "SC1",
                "V1",
                "PO-001",
                800,
                "po_approved",
                None,
                None,
                None,
                None,
                TIMESTAMP,
                TIMESTAMP,
            ),
        )
        conn.execute(
            """
            insert into gr_requests (
              gr_id,
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
              cancelled_by,
              cancelled_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "GR1",
                "PO1",
                "U1",
                100,
                None,
                "pending",
                None,
                "U1",
                TIMESTAMP,
                None,
                None,
                None,
                None,
            ),
        )
        conn.execute(
            """
            insert into gr_requests (
              gr_id,
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
              cancelled_by,
              cancelled_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "GR2",
                "PO1",
                "U1",
                150,
                150,
                "approved",
                None,
                "U1",
                TIMESTAMP,
                "U1",
                TIMESTAMP,
                None,
                None,
            ),
        )
        conn.commit()


def test_compute_sc_budget_sums_pending_approved_and_po_allocation(app_config):
    seed_budget_records(app_config)

    budget = compute_sc_budget(app_config, "SC1")

    assert budget == {
        "sc_amount": 1000.0,
        "sc_pending_total": 100.0,
        "sc_con_value_total": 150.0,
        "sc_available_amount": 750.0,
        "allocated_po_amount": 800.0,
        "unallocated_sc_amount": 200.0,
    }


def test_compute_po_budget_derives_open_po_amount(app_config):
    seed_budget_records(app_config)

    budget = compute_po_budget(app_config, "PO1")

    assert budget == {
        "po_amount": 800.0,
        "po_pending_total": 100.0,
        "po_con_value_total": 150.0,
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
    seed_budget_records(app_config)

    with connect(app_config) as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        ]
        columns = {
            column[1]
            for table_name in table_names
            for column in conn.execute(f"PRAGMA table_info({table_name})")
        }

    assert "open_po_amount" not in columns
    assert compute_po_budget(app_config, "PO1")["open_po_amount"] == 550.0
