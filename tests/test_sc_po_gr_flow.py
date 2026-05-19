import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import ConflictError, PermissionDenied, ValidationError
from sc_gr_app.services.gr_service import approve_gr, create_gr
from sc_gr_app.services.po_service import create_po
from sc_gr_app.services.sc_service import approve_sc, create_sc
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


def seed_approved_sc_vendor_po(
    app_config,
    *,
    sc_no="SC001",
    po_no="PO001",
    po_status="po_approved",
    sc_amount=1000,
    po_amount=800,
):
    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
            "sc_no": sc_no,
            "requester_id": "U1",
            "request_type": "service",
            "cost_center": 1001,
            "sc_amount": sc_amount,
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
        USER,
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
        USER,
        {
            "gr_id": "GR1",
            "po_id": "PO1",
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
        USER,
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
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100},
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


def test_create_po_cannot_exceed_sc_amount(app_config):
    migrate(app_config)
    seed_users(app_config)

    create_sc(
        app_config,
        USER,
        {
            "sc_id": "SC1",
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
        USER,
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
            USER,
            {
                "po_id": "PO2",
                "sc_id": "SC1",
                "vendor_id": "V1",
                "po_amount": 30,
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
            USER,
            {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": amount},
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
            USER,
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
            USER,
            {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100},
        )


def test_create_gr_requires_enough_sc_available(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=1000)
    create_gr(
        app_config,
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 900},
    )

    with pytest.raises(ConflictError, match="SC available amount is insufficient"):
        create_gr(
            app_config,
            USER,
            {"gr_id": "GR2", "po_id": "PO1", "estimated_amount": 101},
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
            USER,
            {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100},
        )


def test_approve_gr_rechecks_extra_con_value(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config, sc_amount=1000, po_amount=1000)
    create_gr(
        app_config,
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 900},
    )

    with pytest.raises(ConflictError, match="SC available amount is insufficient"):
        approve_gr(app_config, ADMIN, "GR1", con_value=1001)


def test_approve_gr_validates_con_value(app_config):
    migrate(app_config)
    seed_users(app_config)
    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100},
    )

    with pytest.raises(ValidationError, match="con_value must be non-negative"):
        approve_gr(app_config, ADMIN, "GR1", con_value=-1)


def test_sc_vendor_po_gr_writes_are_audited(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config)
    create_gr(
        app_config,
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 100},
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
        USER,
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
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 0.1},
    )

    created = create_gr(
        app_config,
        USER,
        {"gr_id": "GR2", "po_id": "PO1", "estimated_amount": 0.2},
    )

    assert created["gr_id"] == "GR2"


def test_approve_gr_allows_exact_decimal_extra_boundary(app_config):
    migrate(app_config)
    seed_users(app_config)

    seed_approved_sc_vendor_po(app_config, sc_amount=0.3, po_amount=0.3)
    create_gr(
        app_config,
        USER,
        {"gr_id": "GR1", "po_id": "PO1", "estimated_amount": 0.1},
    )

    approved = approve_gr(app_config, ADMIN, "GR1", con_value=0.3)

    assert approved["status"] == "approved"
    assert approved["con_value"] == 0.3
