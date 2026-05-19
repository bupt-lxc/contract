import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied, ValidationError
from sc_gr_app.services.vendor_service import create_vendor, search_vendors


USER = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
UNAUTHORIZED = {"user_id": "X1", "role": "viewer", "machine_id": "MX"}


def seed_user(app_config):
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
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()


def test_create_and_search_vendor(app_config):
    migrate(app_config)
    seed_user(app_config)

    created = create_vendor(
        app_config,
        current_user=USER,
        data={
            "vendor_id": "V1",
            "vendor_name": "Alpha Logistics",
            "ksrm_vendor_code": "K001",
            "service_scope": "Transportation",
        },
    )

    results = search_vendors(app_config, text="alpha")

    assert created["vendor_id"] == "V1"
    assert results[0]["vendor_name"] == "Alpha Logistics"


def test_vendor_creation_requires_authorized_role(app_config):
    migrate(app_config)

    with pytest.raises(PermissionDenied):
        create_vendor(
            app_config,
            current_user=UNAUTHORIZED,
            data={
                "vendor_id": "V1",
                "vendor_name": "Alpha Logistics",
                "service_scope": "Transportation",
            },
        )


def test_vendor_creation_validates_required_fields(app_config):
    migrate(app_config)
    seed_user(app_config)

    with pytest.raises(ValidationError, match="vendor_name is required"):
        create_vendor(
            app_config,
            current_user=USER,
            data={
                "vendor_id": "V1",
                "service_scope": "Transportation",
            },
        )


def test_vendor_creation_validates_service_scope(app_config):
    migrate(app_config)
    seed_user(app_config)

    with pytest.raises(ValidationError, match="service_scope is invalid"):
        create_vendor(
            app_config,
            current_user=USER,
            data={
                "vendor_id": "V1",
                "vendor_name": "Alpha Logistics",
                "service_scope": "Unsupported Scope",
            },
        )


def test_vendor_write_is_audited(app_config):
    migrate(app_config)
    seed_user(app_config)

    create_vendor(
        app_config,
        current_user=USER,
        data={
            "vendor_id": "V1",
            "vendor_name": "Alpha Logistics",
            "service_scope": "Transportation",
        },
    )

    with connect(app_config) as conn:
        rows = conn.execute(
            "select action_type, object_type, object_id, sc_id from audit_logs"
        ).fetchall()

    assert [dict(row) for row in rows] == [
        {
            "action_type": "create_vendor",
            "object_type": "vendor",
            "object_id": "V1",
            "sc_id": None,
        }
    ]
