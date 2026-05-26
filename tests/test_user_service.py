import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied
from sc_gr_app.services import user_service
from sc_gr_app.services.user_service import seed_users


def test_seed_users_creates_users_when_empty(app_config):
    """seed_users inserts all six users when none exist."""
    migrate(app_config)
    seed_users(app_config)
    with connect(app_config) as conn:
        rows = conn.execute(
            "select machine_id, user_name, role, email from users order by user_name"
        ).fetchall()
    assert len(rows) == 6
    assert rows[0]["machine_id"] == "V2SE7PP"
    assert rows[0]["user_name"] == "Li, Xingchen (C/EV-L)"
    assert rows[0]["role"] == "requester"
    assert rows[0]["email"] == "xingchen.li@audi.com.cn"


def test_seed_users_is_idempotent(app_config):
    """Calling seed_users twice does not duplicate users."""
    migrate(app_config)
    seed_users(app_config)
    seed_users(app_config)
    with connect(app_config) as conn:
        count = conn.execute("select count(*) as cnt from users").fetchone()["cnt"]
    assert count == 6


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
