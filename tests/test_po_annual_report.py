import sqlite3

import pytest

from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied, ValidationError
from sc_gr_app.services import po_service


ADMIN = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "M_ADMIN"}
REQUESTER = {"user_id": "U_REQ", "role": "requester", "machine_id": "M_REQ"}


def _seed(config):
    migrate(config)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(
        """
        INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
        VALUES
          ('U_ADMIN', 'M_ADMIN', 'Admin User', 'admin', 'admin@test.local', 'active', '2025-01-01', '2025-01-01'),
          ('U_REQ', 'M_REQ', 'Requester One', 'requester', 'req@test.local', 'active', '2025-01-01', '2025-01-01');

        INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('V1', 'Vendor One', 'General', 'U_ADMIN', '2025-01-01', '2025-01-01');

        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at
        )
        VALUES
          ('SC_APPROVED', 'SC-APP-001', 'U_REQ', 'new', 1000, 10000, '2025-01-01', '2025-12-31', 'approved', 'Approved service', 'U_ADMIN', '2025-01-01', '2025-01-01'),
          ('SC_APPROVED_DRAFT_ONLY', 'SC-APP-002', 'U_REQ', 'new', 2000, 20000, '2025-01-01', '2025-12-31', 'approved', 'No qualifying PO', 'U_ADMIN', '2025-01-01', '2025-01-01'),
          ('SC_DRAFT', 'SC-DRAFT-001', 'U_REQ', 'new', 3000, 30000, '2025-01-01', '2025-12-31', 'draft', 'Draft parent', 'U_ADMIN', '2025-01-01', '2025-01-01');

        INSERT INTO pos (
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
          contract_from, contract_to, created_at, updated_at, finished_at, request_type
        )
        VALUES
          ('PO_ACTIVE_APPROVED', 'SC_APPROVED', 'V1', 'PO-ACT-APP', 'U_REQ', 6000, 'active', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_DRAFT_APPROVED', 'SC_APPROVED', 'V1', 'PO-DRAFT-APP', 'U_REQ', 1000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_DRAFT_ONLY', 'SC_APPROVED_DRAFT_ONLY', 'V1', 'PO-DRAFT-ONLY', 'U_REQ', 1000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_WITH_YEAR_GR', 'SC_DRAFT', 'V1', 'PO-YEAR-GR', 'U_REQ', 5000, 'draft', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, NULL),
          ('PO_ACTIVE_INDEPENDENT', NULL, 'V1', 'PO-ACT-FC', 'U_REQ', 7000, 'active', '2025-01-01', '2025-12-31', '2025-01-01', '2025-01-01', NULL, 'FC'),
          ('PO_FINISHED_2025', 'SC_DRAFT', 'V1', 'PO-FIN-2025', 'U_REQ', 8000, 'finished', '2025-01-01', '2025-12-31', '2025-01-01', '2025-06-01', '2025-06-01', NULL),
          ('PO_FINISHED_2024', 'SC_DRAFT', 'V1', 'PO-FIN-2024', 'U_REQ', 9000, 'finished', '2024-01-01', '2024-12-31', '2024-01-01', '2024-06-01', '2024-06-01', NULL);

        INSERT INTO gr_requests (
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          status, created_by, created_at, approved_date, finished_at
        )
        VALUES
          ('GR_PREV', 'GR-PREV', 'PO_ACTIVE_APPROVED', 'U_REQ', 120, 120, 'approved', 'U_ADMIN', '2024-05-01', '2024-05-02', NULL),
          ('GR_SELECTED', 'GR-SEL', 'PO_ACTIVE_APPROVED', 'U_REQ', 250, 250, 'finished', 'U_ADMIN', '2025-05-01', '2025-05-02', '2025-05-03'),
          ('GR_PENDING', 'GR-PENDING', 'PO_ACTIVE_APPROVED', 'U_REQ', 999, NULL, 'pending', 'U_ADMIN', '2025-05-01', NULL, NULL),
          ('GR_DRAFT_PARENT', 'GR-DRAFT-PARENT', 'PO_WITH_YEAR_GR', 'U_REQ', 300, 300, 'approved', 'U_ADMIN', '2025-02-01', '2025-02-02', NULL);

        INSERT INTO po_manual_amounts (
          manual_amount_id, po_id, year, type, amount, created_by, created_at
        )
        VALUES
          ('PMA-PREV', 'PO_ACTIVE_APPROVED', '2024', 'provision', -10, 'U_REQ', '2025-01-01'),
          ('PMA-TBG', 'PO_ACTIVE_APPROVED', '2025', 'to_be_gr', 222, 'U_REQ', '2025-01-01'),
          ('PMA-OTHER-YEAR', 'PO_ACTIVE_APPROVED', '2026', 'to_be_gr', 999, 'U_REQ', '2025-01-01'),
          ('PMA-OTHER-PO', 'PO_ACTIVE_INDEPENDENT', '2024', 'provision', 333, 'U_REQ', '2025-01-01'),
          ('PMA-DRAFT-ONLY', 'PO_DRAFT_ONLY', '2024', 'provision', 444, 'U_REQ', '2025-01-01');
        """
    )
    conn.commit()
    conn.close()


def _by_po(rows):
    return {row["po_no"]: row for row in rows if row["row_type"] == "po"}


def _by_sc(rows):
    return {row["sc_no"]: row for row in rows if row["row_type"] == "sc"}


def test_po_annual_report_includes_qualifying_po_rows_and_sc_only_rows(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)

    po_rows = _by_po(rows)
    sc_rows = _by_sc(rows)
    assert "PO-ACT-APP" in po_rows
    assert "PO-DRAFT-APP" not in po_rows
    assert "PO-DRAFT-ONLY" not in po_rows
    assert "PO-YEAR-GR" in po_rows
    assert "PO-ACT-FC" in po_rows
    assert "PO-FIN-2025" in po_rows
    assert "PO-FIN-2024" not in po_rows
    assert "SC-APP-002" in sc_rows
    assert sc_rows["SC-APP-002"]["requester"] == "Requester One"
    assert sc_rows["SC-APP-002"]["po_no"] == ""
    assert sc_rows["SC-APP-002"]["po_amount"] == ""
    assert sc_rows["SC-APP-002"]["previous_year_gr"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_gr"] == ""
    assert sc_rows["SC-APP-002"]["previous_year_provision"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_to_be_gr"] == ""
    assert "PO-DRAFT-ONLY" not in po_rows


def test_po_annual_report_maps_amounts_and_blank_columns(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)
    row = _by_po(rows)["PO-ACT-APP"]

    assert row["requester"] == "Requester One"
    assert row["sc_no"] == "SC-APP-001"
    assert row["short_text"] == "Approved service"
    assert row["sc_amount"] == 10000
    assert row["po_amount"] == 6000
    assert row["previous_year_gr"] == 120
    assert row["selected_year_gr"] == 250
    assert row["previous_year_provision"] == -10
    assert row["selected_year_to_be_gr"] == 222
    assert row["selected_year_fc_gr"] == ""
    assert row["remark"] == ""


def test_po_annual_report_rejects_invalid_year_and_non_admin(app_config):
    _seed(app_config)

    with pytest.raises(ValidationError):
        po_service.get_annual_report_data(app_config, "25", ADMIN)
    with pytest.raises(ValidationError):
        po_service.get_annual_report_data(app_config, "202A", ADMIN)
    with pytest.raises(PermissionDenied):
        po_service.get_annual_report_data(app_config, "2025", REQUESTER)


def test_po_annual_report_manual_records_do_not_expand_selection_scope(app_config):
    _seed(app_config)

    rows = po_service.get_annual_report_data(app_config, "2025", ADMIN)
    independent = _by_po(rows)["PO-ACT-FC"]
    po_rows = _by_po(rows)
    sc_rows = _by_sc(rows)

    assert independent["previous_year_provision"] == 333
    assert independent["selected_year_to_be_gr"] == ""
    assert "PO-DRAFT-ONLY" not in po_rows
    assert sc_rows["SC-APP-002"]["previous_year_provision"] == ""
    assert sc_rows["SC-APP-002"]["selected_year_to_be_gr"] == ""
