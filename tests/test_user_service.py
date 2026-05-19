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


def test_seed_default_admin_same_machine_creates_one_row_and_preserves_original(
    app_config, monkeypatch
):
    migrate(app_config)
    monkeypatch.setattr(user_service, "get_7_digit_id", lambda: "abc1234")

    user_service.seed_default_admin(app_config)
    with connect(app_config) as conn:
        conn.execute(
            """
            update users
            set user_name = ?, email = ?, updated_at = ?
            where user_id = ?
            """,
            (
                "Renamed Admin",
                "admin@example.com",
                "2026-05-19T00:00:00+00:00",
                user_service.DEFAULT_ADMIN_USER_ID,
            ),
        )
        conn.commit()

    user_service.seed_default_admin(app_config)

    with connect(app_config) as conn:
        rows = conn.execute("select * from users").fetchall()

    assert len(rows) == 1
    assert rows[0]["user_name"] == "Renamed Admin"
    assert rows[0]["email"] == "admin@example.com"
    assert rows[0]["updated_at"] == "2026-05-19T00:00:00+00:00"


def test_seed_default_admin_skips_when_default_admin_exists_for_other_machine(
    app_config, monkeypatch
):
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
                user_service.DEFAULT_ADMIN_USER_ID,
                "other-machine",
                "Existing Admin",
                "admin",
                None,
                "active",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()
    monkeypatch.setattr(user_service, "get_7_digit_id", lambda: "abc1234")

    user_service.seed_default_admin(app_config)

    with connect(app_config) as conn:
        rows = conn.execute("select * from users").fetchall()

    assert len(rows) == 1
    assert rows[0]["machine_id"] == "other-machine"


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


def test_get_user_by_machine_id_rejects_disabled_user(app_config):
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
                "disabled",
                "2026-05-19T00:00:00+00:00",
                "2026-05-19T00:00:00+00:00",
            ),
        )
        conn.commit()

    with pytest.raises(PermissionDenied, match="This machine is not authorized"):
        user_service.get_user_by_machine_id(app_config, "abc1234")
