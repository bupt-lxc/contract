import sqlite3

import pytest

from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.services import po_service


ADMIN = {"user_id": "U_ADMIN", "role": "admin", "machine_id": "M_ADMIN"}
PO_REQUESTER = {"user_id": "U_PO", "role": "requester", "machine_id": "M_PO"}
SC_REQUESTER = {"user_id": "U_SC", "role": "requester", "machine_id": "M_SC"}
SC_ASSIGNEE = {"user_id": "U_ASSIGNEE", "role": "requester", "machine_id": "M_ASSIGNEE"}
OTHER = {"user_id": "U_OTHER", "role": "requester", "machine_id": "M_OTHER"}


def _seed(config, po_status="active"):
    migrate(config)
    conn = sqlite3.connect(config.db_path)
    conn.executescript(
        f"""
        INSERT INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
        VALUES
          ('U_ADMIN', 'M_ADMIN', 'Admin User', 'admin', 'admin@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_PO', 'M_PO', 'PO Requester', 'requester', 'po@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_SC', 'M_SC', 'SC Requester', 'requester', 'sc@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_ASSIGNEE', 'M_ASSIGNEE', 'SC Assignee', 'requester', 'assignee@test.local', 'active', '2026-01-01', '2026-01-01'),
          ('U_OTHER', 'M_OTHER', 'Other User', 'requester', 'other@test.local', 'active', '2026-01-01', '2026-01-01');

        INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('V1', 'Vendor One', 'General', 'U_ADMIN', '2026-01-01', '2026-01-01');

        INSERT INTO sc_records (
          sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
          service_period_start, service_period_end, status, description,
          created_by, created_at, updated_at
        )
        VALUES ('SC1', 'SC-001', 'U_SC', 'new', 1000, 10000, '2026-01-01', '2026-12-31', 'approved', 'Approved SC', 'U_ADMIN', '2026-01-01', '2026-01-01');

        INSERT INTO sc_assignees (sc_id, user_id)
        VALUES ('SC1', 'U_ASSIGNEE');

        INSERT INTO pos (
          po_id, sc_id, vendor_id, po_no, requester_id, po_amount, status,
          created_at, updated_at, finished_at
        )
        VALUES
          ('PO1', 'SC1', 'V1', 'PO-001', 'U_PO', 5000, '{po_status}', '2026-01-01', '2026-01-01', '2026-06-01'),
          ('PO_INDEPENDENT', NULL, 'V1', 'PO-INDEP', 'U_PO', 3000, '{po_status}', '2026-01-01', '2026-01-01', '2026-06-01');
        """
    )
    conn.commit()
    conn.close()


def test_create_list_and_delete_manual_amounts(app_config):
    _seed(app_config)

    provision = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": -10}
    )
    to_be_gr = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2026", "type": "to_be_gr", "amount": 0}
    )

    assert provision["manual_amount_id"].startswith("PMA-")
    assert provision["po_id"] == "PO1"
    assert provision["year"] == "2025"
    assert provision["type"] == "provision"
    assert provision["amount"] == -10
    assert provision["created_by"] == "U_ADMIN"
    assert provision["created_by_name"] == "Admin User"
    assert provision["created_at"]

    rows = po_service.list_po_manual_amounts(app_config, ADMIN, "PO1")
    assert [row["manual_amount_id"] for row in rows] == [
        to_be_gr["manual_amount_id"],
        provision["manual_amount_id"],
    ]

    result = po_service.delete_po_manual_amount(
        app_config, ADMIN, provision["manual_amount_id"]
    )
    assert result == {"deleted": True, "manual_amount_id": provision["manual_amount_id"]}
    remaining = po_service.list_po_manual_amounts(app_config, ADMIN, "PO1")
    assert [row["manual_amount_id"] for row in remaining] == [to_be_gr["manual_amount_id"]]


def test_manual_amount_validation_and_duplicate(app_config):
    _seed(app_config)

    with pytest.raises(ValidationError, match="year must be a 4-digit string"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "26", "type": "provision", "amount": 1}
        )
    with pytest.raises(ValidationError, match="type must be"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "other", "amount": 1}
        )
    with pytest.raises(ValidationError, match="amount must be a number"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": "abc"}
        )
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": 1}
    )
    with pytest.raises(ConflictError, match="already exists"):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO1", {"year": "2026", "type": "provision", "amount": 2}
        )
    with pytest.raises(NotFound):
        po_service.create_po_manual_amount(
            app_config, ADMIN, "PO_MISSING", {"year": "2026", "type": "provision", "amount": 1}
        )


def test_manual_amount_mutation_permissions_for_linked_and_independent_pos(app_config):
    _seed(app_config)

    for index, user in enumerate((ADMIN, SC_REQUESTER), start=1):
        created = po_service.create_po_manual_amount(
            app_config,
            user,
            "PO1",
            {"year": str(2020 + index), "type": "provision", "amount": index},
        )
        assert created["created_by"] == user["user_id"]
        assert po_service.delete_po_manual_amount(
            app_config, user, created["manual_amount_id"]
        )["deleted"] is True

    independent = po_service.create_po_manual_amount(
        app_config,
        PO_REQUESTER,
        "PO_INDEPENDENT",
        {"year": "2025", "type": "provision", "amount": 10},
    )
    assert po_service.delete_po_manual_amount(
        app_config, PO_REQUESTER, independent["manual_amount_id"]
    )["deleted"] is True

    for user in (PO_REQUESTER, SC_ASSIGNEE, OTHER):
        with pytest.raises(PermissionDenied):
            po_service.create_po_manual_amount(
                app_config, user, "PO1", {"year": "2026", "type": "provision", "amount": 1}
            )

    with pytest.raises(PermissionDenied):
        po_service.create_po_manual_amount(
            app_config, OTHER, "PO_INDEPENDENT", {"year": "2026", "type": "provision", "amount": 1}
        )


def test_manual_amounts_allowed_on_finished_po(app_config):
    _seed(app_config, po_status="finished")

    created = po_service.create_po_manual_amount(
        app_config, SC_REQUESTER, "PO1", {"year": "2026", "type": "to_be_gr", "amount": 12}
    )

    assert created["amount"] == 12
    assert po_service.delete_po_manual_amount(
        app_config, SC_REQUESTER, created["manual_amount_id"]
    )["deleted"] is True


def test_po_and_sc_detail_include_manual_amounts_and_permission(app_config):
    _seed(app_config)
    created = po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 11}
    )

    po_detail = po_service.get_po_detail(app_config, SC_REQUESTER, "PO1")
    assert po_detail["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert po_detail["manual_amounts"][0]["created_by_name"] == "Admin User"
    assert po_detail["permissions"]["can_manage_po_manual_amounts"] is True

    assignee_detail = po_service.get_po_detail(app_config, SC_ASSIGNEE, "PO1")
    assert assignee_detail["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert assignee_detail["permissions"]["can_manage_po_manual_amounts"] is False

    with pytest.raises(PermissionDenied):
        po_service.get_po_detail(app_config, PO_REQUESTER, "PO1")

    from sc_gr_app.services import sc_service

    sc_detail = sc_service.get_sc_detail(app_config, SC_REQUESTER, "SC1")
    po_row = next(row for row in sc_detail["pos"] if row["po_id"] == "PO1")
    assert po_row["manual_amounts"][0]["manual_amount_id"] == created["manual_amount_id"]
    assert po_row["can_manage_po_manual_amounts"] is True
    assert sc_detail["permissions"]["can_manage_po_manual_amounts"] is True


def test_manual_amounts_do_not_change_po_budget(app_config):
    _seed(app_config)
    before = po_service.get_po_detail(app_config, ADMIN, "PO1")["po"]["open_po_amount"]

    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 999999}
    )

    after = po_service.get_po_detail(app_config, ADMIN, "PO1")["po"]["open_po_amount"]
    assert after == before


def test_delete_po_removes_manual_amounts(app_config):
    _seed(app_config, po_status="draft")
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "provision", "amount": 11}
    )

    po_service.delete_po(app_config, SC_REQUESTER, "PO1")

    with sqlite3.connect(app_config.db_path) as conn:
        count = conn.execute("select count(*) from po_manual_amounts").fetchone()[0]
    assert count == 0


def test_delete_sc_removes_child_po_manual_amounts(app_config):
    _seed(app_config, po_status="draft")
    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute("update sc_records set status = 'draft' where sc_id = 'SC1'")
        conn.commit()
    po_service.create_po_manual_amount(
        app_config, ADMIN, "PO1", {"year": "2025", "type": "to_be_gr", "amount": 22}
    )

    from sc_gr_app.services import sc_service

    sc_service.delete_sc(app_config, SC_REQUESTER, "SC1")

    with sqlite3.connect(app_config.db_path) as conn:
        count = conn.execute("select count(*) from po_manual_amounts").fetchone()[0]
    assert count == 0
