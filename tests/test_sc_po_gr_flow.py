from decimal import Decimal

import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.services.gr_service import approve_gr, cancel_gr, create_gr, update_gr
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.sc_service import approve_sc, close_sc, create_sc
from sc_gr_app.services.vendor_service import create_vendor


USER = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
ADMIN = {"user_id": "A1", "role": "admin", "machine_id": "M2"}
OTHER_USER = {"user_id": "U2", "role": "requester", "machine_id": "M3"}


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


def seed_other_user(app_config):
    with connect(app_config) as conn:
        conn.execute(
            "insert into users values (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "U2",
                "M3",
                "Other Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.commit()


def seed_approved_sc_vendor_po(
    app_config,
    *,
    sc_no="SC001",
    po_no="PO001",
    po_status="po_approved",
    sc_amount=1000,
    po_amount=800,
):
    sc_no_for_approval = sc_no or "SC-TEMP"
    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": sc_no_for_approval,
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": sc_amount,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    approve_sc(app_config, ADMIN, "SC1")
    if sc_no != sc_no_for_approval:
        with connect(app_config) as conn:
            conn.execute(
                "update sc_records set sc_no = ? where sc_id = ?",
                (sc_no, "SC1"),
            )
            conn.commit()
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Vendor",
            "service_scope": "General Service",
        },
    )
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO1",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_no": po_no,
            "po_amount": po_amount,
            "status": po_status,
        },
    )


def test_sc_po_gr_happy_path(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
            "remark": "monthly service",
        },
    )
    approved = approve_gr(app_config, ADMIN, "GR1", con_value=90)

    with connect(app_config) as conn:
        row = conn.execute(
            "select status, con_value from gr_requests where gr_id = 'GR1'"
        ).fetchone()

    assert approved["status"] == "approved"
    assert row["status"] == "approved"
    assert row["con_value"] == 90


def test_approve_gr_rejects_closed_parent_sc(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
        },
    )
    close_sc(app_config, ADMIN, "SC1")

    with pytest.raises(ConflictError, match="Closed SC cannot be edited"):
        approve_gr(app_config, ADMIN, "GR1", con_value=90)


def test_update_gr_rejects_closed_parent_sc(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
        },
    )
    close_sc(app_config, ADMIN, "SC1")

    with pytest.raises(ConflictError, match="Closed SC cannot be edited"):
        update_gr(app_config, ADMIN, "GR1", {"remark": "after close"})


def test_cancel_gr_rejects_closed_parent_sc(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
        },
    )
    close_sc(app_config, ADMIN, "SC1")

    with pytest.raises(ConflictError, match="Closed SC cannot be edited"):
        cancel_gr(app_config, ADMIN, "GR1")


def test_requester_cannot_approve_sc_or_gr(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC001",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    with pytest.raises(PermissionDenied):
        approve_sc(app_config, USER, "SC1")

    approve_sc(app_config, ADMIN, "SC1")
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Vendor",
            "service_scope": "General Service",
        },
    )
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO1",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_no": "PO001",
            "po_amount": 500,
            "status": "po_approved",
        },
    )
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    with pytest.raises(PermissionDenied):
        approve_gr(app_config, USER, "GR1", con_value=90)


def test_backfill_sc_status_requires_admin(app_config):
    migrate(app_config)
    seed_users(app_config)

    with pytest.raises(PermissionDenied):
        create_sc(
            app_config,
            USER,
            {
                "sc_id": "SC1",
                "requester_id": "U1",
                "request_type": "service",
                "cost_center": 1001,
                "sc_amount": 1000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
                "status": "approved",
            },
            operation_mode="backfill",
        )


def test_normal_sc_creation_ignores_supplied_status(app_config):
    migrate(app_config)
    seed_users(app_config)

    created = create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC001",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "status": "approved",
        },
    )

    assert created["status"] == "pending"


def test_create_sc_validates_request_type(app_config):
    migrate(app_config)
    seed_users(app_config)

    with pytest.raises(ValidationError, match="request_type is invalid"):
        create_sc(
            app_config,
            USER,
            {
                "sc_id": "SC1",
                "requester_id": "U1",
                "request_type": "unsupported",
                "cost_center": 1001,
                "sc_amount": 1000,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            },
        )


@pytest.mark.parametrize("sc_amount", [float("nan"), float("inf")])
def test_create_sc_rejects_non_finite_sc_amount(app_config, sc_amount):
    migrate(app_config)
    seed_users(app_config)

    with pytest.raises(ValidationError, match="sc_amount must be positive"):
        create_sc(
            app_config,
            USER,
            {
                "sc_id": "SC1",
                "requester_id": "U1",
                "request_type": "service",
                "cost_center": 1001,
                "sc_amount": sc_amount,
                "service_period_start": "2026-01-01",
                "service_period_end": "2026-12-31",
            },
        )


def test_create_po_cannot_exceed_sc_amount(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC001",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 100,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    approve_sc(app_config, ADMIN, "SC1")
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Vendor",
            "service_scope": "General Service",
        },
    )
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO1",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_amount": 80,
        },
    )

    with pytest.raises(ConflictError, match="exceed SC amount"):
        create_po(
            app_config,
            ADMIN,
            {
                "po_id": "PO2",
                "sc_id": "SC1",
                "vendor_id": "V1",
                "po_amount": 30,
            },
        )


@pytest.mark.parametrize("po_amount", [Decimal("NaN"), Decimal("Infinity")])
def test_create_po_rejects_non_finite_po_amount(app_config, po_amount):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_amount=100)

    with pytest.raises(ValidationError, match="po_amount must be positive"):
        create_po(
            app_config,
            ADMIN,
            {
                "po_id": "PO2",
                "sc_id": "SC1",
                "vendor_id": "V1",
                "po_amount": po_amount,
            },
        )


@pytest.mark.parametrize(
    ("sc_no", "po_no", "po_status", "amount", "message"),
    [
        ("", "PO001", "po_approved", 100, "SC No is required"),
        ("SC001", "", "po_approved", 100, "PO No is required"),
        ("SC001", "PO001", "po_pending", 100, "PO must be approved"),
        ("SC001", "PO001", "po_approved", 900, "PO open amount is insufficient"),
    ],
)
def test_create_gr_requires_complete_approved_sc_and_po(
    app_config,
    sc_no,
    po_no,
    po_status,
    amount,
    message,
):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(
        app_config,
        sc_no=sc_no,
        po_no=po_no,
        po_status=po_status,
        po_amount=800,
    )

    with pytest.raises(ConflictError, match=message):
        create_gr(
            app_config,
            ADMIN,
            {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": amount},
        )


def test_create_po_requires_approved_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC001",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Vendor",
            "service_scope": "General Service",
        },
    )

    with pytest.raises(ConflictError, match="SC must be approved"):
        create_po(
            app_config,
            ADMIN,
            {
                "po_id": "PO1",
                "sc_id": "SC1",
                "vendor_id": "V1",
                "po_amount": 800,
            },
        )


def test_create_gr_requires_approved_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": "SC001",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    create_vendor(
        app_config,
        USER,
        {
            "vendor_id": "V1",
            "vendor_name": "Vendor",
            "service_scope": "General Service",
        },
    )

    with connect(app_config) as conn:
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
                "PO001",
                800,
                "po_approved",
                None,
                None,
                None,
                None,
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()

    with pytest.raises(ConflictError, match="SC must be approved"):
        create_gr(
            app_config,
            ADMIN,
            {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
        )


def test_create_gr_requires_enough_sc_available(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=1000)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 900},
    )

    with pytest.raises(ConflictError, match="SC available amount is insufficient"):
        create_gr(
            app_config,
            ADMIN,
            {"gr_id": "GR2", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 101},
        )


@pytest.mark.parametrize(
    "estimated_amount",
    [Decimal("NaN"), Decimal("Infinity")],
)
def test_create_gr_rejects_non_finite_estimated_amount(
    app_config,
    estimated_amount,
):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    with pytest.raises(
        ValidationError,
        match="estimated_amount must be positive",
    ):
        create_gr(
            app_config,
            ADMIN,
            {
                "gr_id": "GR1",
                "po_id": "PO1",
                "requester_id": "U1",
                "estimated_amount": estimated_amount,
            },
        )


def test_create_gr_rejects_approved_gr_with_null_con_value(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    with connect(app_config) as conn:
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
                "GR_BAD",
                "PO1",
                "U1",
                100,
                None,
                "approved",
                None,
                "U1",
                "2026-05-19T00:00:00+00:00",
                "A1",
                "2026-05-19T00:00:00+00:00",
                None,
                None,
            ),
        )
        conn.commit()

    with pytest.raises(ConflictError, match="Approved GR has NULL con_value"):
        create_gr(
            app_config,
            ADMIN,
            {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
        )


def test_approve_gr_rechecks_extra_con_value(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=1000)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 900},
    )

    with pytest.raises(ConflictError, match="SC available amount is insufficient"):
        approve_gr(app_config, ADMIN, "GR1", con_value=1001)


def test_approve_gr_validates_con_value(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    with pytest.raises(ValidationError, match="con_value must be non-negative"):
        approve_gr(app_config, ADMIN, "GR1", con_value=-1)


@pytest.mark.parametrize("con_value", [Decimal("NaN"), Decimal("Infinity")])
def test_approve_gr_rejects_non_finite_con_value(app_config, con_value):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    with pytest.raises(ValidationError, match="con_value must be non-negative"):
        approve_gr(app_config, ADMIN, "GR1", con_value=con_value)


def test_sc_vendor_po_gr_writes_are_audited(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )
    approve_gr(app_config, ADMIN, "GR1", con_value=90)

    with connect(app_config) as conn:
        actions = [
            row["action_type"]
            for row in conn.execute(
                "select action_type from audit_logs order by created_at"
            )
        ]

    assert actions == [
        "create_sc",
        "approve_sc",
        "create_vendor",
        "create_po",
        "create_gr",
        "approve_gr",
    ]


def test_create_po_allows_exact_decimal_budget_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config, sc_amount=0.3, po_amount=0.1)

    created = create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO2",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_amount": 0.2,
            "status": "po_approved",
        },
    )

    assert created["po_id"] == "PO2"


def test_create_gr_allows_exact_decimal_budget_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config, sc_amount=0.3, po_amount=0.3)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 0.1},
    )

    created = create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR2", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 0.2},
    )

    assert created["gr_id"] == "GR2"


def test_approve_gr_allows_exact_decimal_extra_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config, sc_amount=0.3, po_amount=0.3)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 0.1},
    )

    approved = approve_gr(app_config, ADMIN, "GR1", con_value=0.3)

    assert approved["status"] == "approved"
    assert approved["con_value"] == 0.3


def test_requester_creates_minimal_draft_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft

    created = create_sc_draft(
        app_config,
        USER,
        {"sc_id": "SC_DRAFT", "requester_id": "U1"},
    )

    assert created["status"] == "draft"
    assert created["requester_id"] == "U1"
    assert created["request_type"] is None
    assert created["sc_amount"] is None


def test_requester_cannot_create_draft_for_another_owner(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_other_user(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft

    with pytest.raises(PermissionDenied):
        create_sc_draft(
            app_config,
            USER,
            {"sc_id": "SC_DRAFT", "requester_id": "U2"},
        )


def test_submit_draft_requires_business_fields_but_not_sc_no(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})

    with pytest.raises(ValidationError, match="request_type is required"):
        submit_sc(app_config, USER, "SC_DRAFT", {})

    submitted = submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    assert submitted["status"] == "pending"
    assert submitted["sc_no"] is None


def test_owner_cannot_edit_pending_sc(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc, update_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    with pytest.raises(PermissionDenied):
        update_sc(app_config, USER, "SC_DRAFT", {"description": "late change"})


def test_admin_cannot_approve_sc_without_sc_no(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )

    with pytest.raises(ConflictError, match="SC No is required"):
        approve_sc(app_config, ADMIN, "SC_DRAFT")


def test_admin_updates_pending_sc_then_approves_denies_and_closes(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import (
        close_sc,
        create_sc_draft,
        deny_sc,
        submit_sc,
        update_sc,
    )

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})
    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    updated = update_sc(app_config, ADMIN, "SC_DRAFT", {"sc_no": "SC001"})
    approved = approve_sc(app_config, ADMIN, "SC_DRAFT")
    closed = close_sc(app_config, ADMIN, "SC_DRAFT")

    assert updated["sc_no"] == "SC001"
    assert approved["status"] == "approved"
    assert closed["status"] == "closed"

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC_DENY",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 100,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    denied = deny_sc(app_config, ADMIN, "SC_DENY")
    assert denied["status"] == "denied"


def test_get_sc_detail_returns_related_data_and_permissions(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import get_sc_detail

    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
        },
    )

    detail = get_sc_detail(app_config, ADMIN, "SC1")
    requester_detail = get_sc_detail(app_config, USER, "SC1")

    assert detail["sc"]["sc_id"] == "SC1"
    assert detail["budget"]["sc_amount"] == 1000
    assert [po["po_id"] for po in detail["pos"]] == ["PO1"]
    assert [gr["gr_id"] for gr in detail["grs"]] == ["GR1"]
    assert "create_sc" in [log["action_type"] for log in detail["audit_logs"]]
    assert detail["permissions"] == {
        "can_edit_sc": True,
        "can_submit_sc": False,
        "can_approve_sc": False,
        "can_deny_sc": False,
        "can_close_sc": True,
        "can_manage_po": True,
        "can_manage_gr": True,
    }
    assert requester_detail["permissions"]["can_manage_po"] is False
    assert requester_detail["permissions"]["can_manage_gr"] is False


def test_get_sc_detail_includes_po_budget_data(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_amount=800)
    create_gr(
            app_config,
            ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    from sc_gr_app.services.sc_service import get_sc_detail

    detail = get_sc_detail(app_config, ADMIN, "SC1")

    assert detail["pos"][0]["budget"]["po_amount"] == 800
    assert detail["pos"][0]["budget"]["open_po_amount"] == 700
    assert detail["pos"][0]["open_po_amount"] == 700


def test_admin_cannot_view_draft_sc_detail(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, get_sc_detail

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})

    with pytest.raises(PermissionDenied, match="SC is not visible"):
        get_sc_detail(app_config, ADMIN, "SC_DRAFT")


def test_update_sc_rejects_amount_below_allocated_po_amount(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=800)

    from sc_gr_app.services.sc_service import update_sc

    with pytest.raises(ConflictError, match="below allocated PO amount"):
        update_sc(app_config, ADMIN, "SC1", {"sc_amount": 799})


def test_update_sc_rejects_amount_below_gr_budget_usage(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=1000)
    create_gr(
        app_config,
        ADMIN, {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 300})
    approve_gr(app_config, ADMIN, "GR1", con_value=900)
    with connect(app_config) as conn:
        conn.execute("update pos set po_amount = ? where po_id = ?", (100, "PO1"))
        conn.commit()

    from sc_gr_app.services.sc_service import update_sc

    with pytest.raises(ConflictError, match="below GR usage"):
        update_sc(app_config, ADMIN, "SC1", {"sc_amount": 899})


def test_update_sc_allows_exact_decimal_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1, po_amount=0.1)
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO2",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_amount": 0.2,
            "status": "po_approved",
        },
    )

    from sc_gr_app.services.sc_service import update_sc

    updated = update_sc(app_config, ADMIN, "SC1", {"sc_amount": Decimal("0.3")})

    assert updated["sc_amount"] == 0.3


def test_update_sc_rejects_invalid_service_period_for_draft_and_admin(app_config):
    migrate(app_config)
    seed_users(app_config)

    from sc_gr_app.services.sc_service import create_sc_draft, submit_sc, update_sc

    create_sc_draft(app_config, USER, {"sc_id": "SC_DRAFT", "requester_id": "U1"})

    with pytest.raises(ValidationError, match="service period is invalid"):
        update_sc(
            app_config,
            USER,
            "SC_DRAFT",
            {
                "service_period_start": "2026-12-31",
                "service_period_end": "2026-01-01",
            },
        )

    submit_sc(
        app_config,
        USER,
        "SC_DRAFT",
        {
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": 1000,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
            "sc_no": "SC001",
        },
    )

    with pytest.raises(ValidationError, match="service period is invalid"):
        update_sc(
            app_config,
            ADMIN,
            "SC_DRAFT",
            {
                "service_period_start": "2027-01-01",
                "service_period_end": "2026-12-31",
            },
        )


@pytest.mark.parametrize(
    "field",
    [
        "request_type",
        "cost_center",
        "sc_amount",
        "service_period_start",
        "service_period_end",
    ],
)
@pytest.mark.parametrize("empty_value", [None, ""])
def test_update_sc_rejects_clearing_required_fields_on_non_draft(
    app_config,
    field,
    empty_value,
):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    from sc_gr_app.services.sc_service import update_sc

    with pytest.raises(ValidationError, match=f"{field} is required"):
        update_sc(app_config, ADMIN, "SC1", {field: empty_value})


def test_po_writes_require_admin(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    from sc_gr_app.services.po_service import approve_po, finish_po, update_po

    with pytest.raises(PermissionDenied):
        create_po(
            app_config,
            USER,
            {
                "po_id": "PO2",
                "sc_id": "SC1",
                "vendor_id": "V1",
                "po_amount": 100,
            },
        )
    with pytest.raises(PermissionDenied):
        update_po(app_config, USER, "PO1", {"po_no": "PO002"})
    with pytest.raises(PermissionDenied):
        approve_po(app_config, USER, "PO1")
    with pytest.raises(PermissionDenied):
        finish_po(app_config, USER, "PO1")


def test_admin_updates_po_with_budget_validation(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_amount=800)
    create_gr(
        app_config,
        ADMIN, {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 300})

    from sc_gr_app.services.po_service import update_po

    with pytest.raises(ConflictError, match="below GR usage"):
        update_po(app_config, ADMIN, "PO1", {"po_amount": 299})

    updated = update_po(
        app_config,
        ADMIN,
        "PO1",
        {
            "po_no": "PO002",
            "po_amount": 500,
            "contract_no": "CTR-001",
            "payment_frequency": "monthly",
        },
    )

    assert updated["po_no"] == "PO002"
    assert updated["po_amount"] == 500
    assert updated["contract_no"] == "CTR-001"


def test_admin_approves_and_finishes_po(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_status="po_pending")

    from sc_gr_app.services.po_service import approve_po, finish_po

    approved = approve_po(app_config, ADMIN, "PO1")
    finished = finish_po(app_config, ADMIN, "PO1")

    assert approved["status"] == "po_approved"
    assert finished["status"] == "finished"


def test_update_po_rejects_invalid_vendor_closed_sc_and_sc_overallocation(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=800)

    from sc_gr_app.services.po_service import update_po

    with pytest.raises(NotFound, match="Vendor not found"):
        update_po(app_config, ADMIN, "PO1", {"vendor_id": "MISSING"})

    with pytest.raises(ConflictError, match="exceed SC amount"):
        update_po(app_config, ADMIN, "PO1", {"po_amount": 1001})

    with connect(app_config) as conn:
        conn.execute("update sc_records set status = 'closed' where sc_id = 'SC1'")
        conn.commit()

    with pytest.raises(ConflictError, match="Closed SC cannot be edited"):
        update_po(app_config, ADMIN, "PO1", {"po_no": "PO-CLOSED"})


def test_update_po_allows_exact_decimal_sibling_budget_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=0.6, po_amount=0.1)
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO2",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_amount": 0.2,
        },
    )
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO3",
            "sc_id": "SC1",
            "vendor_id": "V1",
            "po_amount": 0.1,
        },
    )

    from sc_gr_app.services.po_service import update_po

    updated = update_po(app_config, ADMIN, "PO3", {"po_amount": 0.3})

    assert updated["po_amount"] == 0.3


def test_update_po_allows_exact_decimal_gr_usage_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1, po_amount=1)
    create_gr(
        app_config,
        ADMIN, {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 0.1})
    create_gr(
        app_config,
        ADMIN, {"gr_id": "GR2", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 0.2})
    approve_gr(app_config, ADMIN, "GR2", con_value=0.2)

    from sc_gr_app.services.po_service import update_po

    updated = update_po(app_config, ADMIN, "PO1", {"po_amount": 0.3})

    assert updated["po_amount"] == 0.3


def test_po_status_transitions_require_current_status(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_status="po_approved")

    from sc_gr_app.services.po_service import approve_po, finish_po

    with pytest.raises(ConflictError, match="PO must be pending"):
        approve_po(app_config, ADMIN, "PO1")

    finish_po(app_config, ADMIN, "PO1")

    with pytest.raises(ConflictError, match="PO must be approved"):
        finish_po(app_config, ADMIN, "PO1")


def test_po_update_approve_finish_are_audited(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, po_status="po_pending")

    from sc_gr_app.services.po_service import approve_po, finish_po, update_po

    update_po(app_config, ADMIN, "PO1", {"po_no": "PO002"})
    approve_po(app_config, ADMIN, "PO1")
    finish_po(app_config, ADMIN, "PO1")

    with connect(app_config) as conn:
        actions = [
            row["action_type"]
            for row in conn.execute(
                "select action_type from audit_logs order by created_at"
            )
        ]

    assert actions[-3:] == ["update_po", "approve_po", "finish_po"]


def test_gr_writes_require_admin(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    from sc_gr_app.services.gr_service import cancel_gr, update_gr

    with pytest.raises(PermissionDenied):
        create_gr(
            app_config,
            USER,
            {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
        )

    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    with pytest.raises(PermissionDenied):
        update_gr(app_config, USER, "GR1", {"remark": "changed"})
    with pytest.raises(PermissionDenied):
        cancel_gr(app_config, USER, "GR1")


def test_admin_create_gr_preserves_business_requester_and_creator(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)

    created = create_gr(
        app_config,
        ADMIN,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
            "requester_id": "U1",
            "estimated_amount": 100,
        },
    )

    assert created["requester_id"] == "U1"
    assert created["created_by"] == "A1"


def test_admin_updates_pending_gr_with_budget_validation(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=500, po_amount=500)
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    from sc_gr_app.services.gr_service import update_gr

    with pytest.raises(ConflictError, match="available amount is insufficient"):
        update_gr(app_config, ADMIN, "GR1", {"estimated_amount": 600})

    updated = update_gr(
        app_config,
        ADMIN,
        "GR1",
        {"estimated_amount": 200, "remark": "updated"},
    )

    assert updated["estimated_amount"] == 200
    assert updated["remark"] == "updated"


def test_admin_moves_pending_gr_between_pos_on_same_sc_using_sc_delta(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=300, po_amount=300)
    with connect(app_config) as conn:
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
                "PO2",
                "SC1",
                "V1",
                "PO002",
                200,
                "po_approved",
                None,
                None,
                None,
                None,
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.commit()
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR2", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 150},
    )

    from sc_gr_app.services.gr_service import update_gr

    updated = update_gr(
        app_config,
        ADMIN,
        "GR1",
        {"po_id": "PO2", "estimated_amount": 150},
    )

    assert updated["po_id"] == "PO2"
    assert updated["estimated_amount"] == 150


def test_cross_sc_pending_gr_move_writes_audit_for_both_scs(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=500, po_amount=500)
    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC2",
            "sc_no": "SC002",
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 2002,
            "sc_amount": 500,
            "service_period_start": "2026-01-01",
            "service_period_end": "2026-12-31",
        },
    )
    approve_sc(app_config, ADMIN, "SC2")
    create_po(
        app_config,
        ADMIN,
        {
            "po_id": "PO2",
            "sc_id": "SC2",
            "vendor_id": "V1",
            "po_no": "PO002",
            "po_amount": 500,
            "status": "po_approved",
        },
    )
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    from sc_gr_app.services.gr_service import update_gr

    update_gr(app_config, ADMIN, "GR1", {"po_id": "PO2"})

    with connect(app_config) as conn:
        audit_sc_ids = [
            row["sc_id"]
            for row in conn.execute(
                """
                select sc_id
                from audit_logs
                where action_type = 'update_gr' and object_id = 'GR1'
                order by sc_id
                """
            )
        ]

    assert audit_sc_ids == ["SC1", "SC2"]


@pytest.mark.parametrize("requester_id", [None, ""])
def test_update_pending_gr_rejects_blank_requester_id(app_config, requester_id):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    from sc_gr_app.services.gr_service import update_gr

    with pytest.raises(ValidationError, match="requester_id is required"):
        update_gr(app_config, ADMIN, "GR1", {"requester_id": requester_id})


def test_update_pending_gr_rejects_unknown_requester_id(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )

    from sc_gr_app.services.gr_service import update_gr

    with pytest.raises(NotFound, match="User not found: MISSING"):
        update_gr(app_config, ADMIN, "GR1", {"requester_id": "MISSING"})


def test_admin_updates_approved_gr_con_value_and_cancels_pending_gr(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR1", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 100},
    )
    approve_gr(app_config, ADMIN, "GR1", con_value=90)
    create_gr(
        app_config,
        ADMIN,
        {"gr_id": "GR2", "po_id": "PO1", "requester_id": "U1", "estimated_amount": 50},
    )

    from sc_gr_app.services.gr_service import cancel_gr, update_gr

    updated = update_gr(
        app_config,
        ADMIN,
        "GR1",
        {"con_value": 95, "remark": "invoice adjusted"},
    )
    cancelled = cancel_gr(app_config, ADMIN, "GR2")

    assert updated["con_value"] == 95
    assert updated["remark"] == "invoice adjusted"
    assert cancelled["status"] == "cancelled"
