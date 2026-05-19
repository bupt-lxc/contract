import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied
from sc_gr_app.services import user_service


def test_seed_default_admin_creates_active_admin_for_machine_id(
    app_config, monkeypatch
):
    migrate(app_config)
    monkeypatch.setattr(user_service, "get_7_digit_id", lambda: "abc1234")

    user_service.seed_default_admin(app_config)

    with connect(app_config) as conn:
        row = conn.execute("select * from users").fetchone()

    assert dict(row) | {"created_at": None, "updated_at": None} == {
        "user_id": "U-ADMIN",
        "machine_id": "abc1234",
        "user_name": "Default Admin",
        "role": "admin",
        "email": None,
        "status": "active",
        "created_at": None,
        "updated_at": None,
    }
    assert row["created_at"]
    assert row["updated_at"]


def test_seed_default_admin_requires_machine_id(app_config, monkeypatch):
    migrate(app_config)
    monkeypatch.setattr(user_service, "get_7_digit_id", lambda: "")

    with pytest.raises(PermissionDenied, match="Failed to get Windows user ID"):
        user_service.seed_default_admin(app_config)


def test_get_user_by_machine_id_returns_active_user(app_config):
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
                "U-1",
                "abc1234",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()

    user = user_service.get_user_by_machine_id(app_config, "abc1234")

    assert user["user_id"] == "U-1"
    assert user["machine_id"] == "abc1234"


def test_get_user_by_machine_id_rejects_missing_machine(app_config):
    migrate(app_config)

    with pytest.raises(PermissionDenied, match="This machine is not authorized"):
        user_service.get_user_by_machine_id(app_config, "missing")
