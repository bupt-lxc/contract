import pytest

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.errors import PermissionDenied, NotFound, ValidationError
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
    assert rows[0]["role"] == "admin"
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


def test_create_user(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    result = user_service.create_user(app_config, current_user, {
        "machine_id": "NEWUSER",
        "user_name": "Test User",
        "email": "test@example.com",
        "role": "requester",
    })
    assert result["user_id"] == "U-NEWUSER"
    assert result["user_name"] == "Test User"
    assert result["role"] == "requester"
    assert result["status"] == "active"
    with connect(app_config) as conn:
        row = conn.execute("select * from users where machine_id = ?", ("NEWUSER",)).fetchone()
    assert row is not None
    assert row["user_name"] == "Test User"


def test_create_user_requires_admin(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-REQ", "role": "requester", "machine_id": "REQ001"}
    with pytest.raises(PermissionDenied, match="Only admins can create users"):
        user_service.create_user(app_config, current_user, {
            "machine_id": "NEWUSER",
            "user_name": "Test",
            "email": "t@t.com",
            "role": "requester",
        })


def test_create_user_duplicate(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    user_service.create_user(app_config, current_user, {
        "machine_id": "DUPUSER",
        "user_name": "First",
        "email": "first@example.com",
        "role": "requester",
    })
    with pytest.raises(ValidationError, match="already exists"):
        user_service.create_user(app_config, current_user, {
            "machine_id": "DUPUSER",
            "user_name": "Second",
            "email": "second@example.com",
            "role": "requester",
        })


def test_update_user(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    user_service.create_user(app_config, current_user, {
        "machine_id": "EDITME",
        "user_name": "Original",
        "email": "old@example.com",
        "role": "requester",
    })
    result = user_service.update_user(app_config, current_user, "EDITME", {
        "user_name": "Updated Name",
        "email": "new@example.com",
    })
    assert result["user_name"] == "Updated Name"
    assert result["email"] == "new@example.com"
    with connect(app_config) as conn:
        row = conn.execute("select * from users where machine_id = ?", ("EDITME",)).fetchone()
    assert row["user_name"] == "Updated Name"
    assert row["email"] == "new@example.com"


def test_update_user_requires_admin(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-REQ", "role": "requester", "machine_id": "REQ001"}
    with pytest.raises(PermissionDenied, match="Only admins can update users"):
        user_service.update_user(app_config, current_user, "SOMEONE", {"user_name": "X"})


def test_disable_user(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    user_service.create_user(app_config, current_user, {
        "machine_id": "DISABLEME",
        "user_name": "To Disable",
        "email": "d@d.com",
        "role": "requester",
    })
    result = user_service.disable_user(app_config, current_user, "DISABLEME")
    assert result["status"] == "disabled"
    with connect(app_config) as conn:
        row = conn.execute("select status from users where machine_id = ?", ("DISABLEME",)).fetchone()
    assert row["status"] == "disabled"


def test_disable_user_cannot_disable_self(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "ADMIN01"}
    with pytest.raises(ValidationError, match="Cannot disable your own account"):
        user_service.disable_user(app_config, current_user, "ADMIN01")


def test_disable_user_not_found(app_config):
    migrate(app_config)
    current_user = {"user_id": "U-ADMIN", "role": "admin", "machine_id": "TEST001"}
    with pytest.raises(NotFound, match="not found"):
        user_service.disable_user(app_config, current_user, "NONEXIST")


class TestSeedUsersSkipWhenNotEmpty:
    def test_seed_users_inserts_when_table_empty(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)
        seed_users(app_config)

        with connect(app_config) as conn:
            count = conn.execute("select count(*) as cnt from users").fetchone()["cnt"]
        assert count == 6

    def test_seed_users_skips_when_users_exist(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)

        with connect(app_config) as conn:
            conn.execute(
                "insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
                "values ('U-CUSTOM', 'CUSTOM01', 'Custom User', 'admin', 'custom@test.com', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            conn.commit()

        seed_users(app_config)

        with connect(app_config) as conn:
            users = conn.execute("select * from users").fetchall()
        assert len(users) == 1
        assert users[0]["machine_id"] == "CUSTOM01"
        assert users[0]["role"] == "admin"

    def test_seed_users_preserves_existing_roles(self, app_config):
        from sc_gr_app.db.migrations import migrate
        from sc_gr_app.services.user_service import seed_users

        migrate(app_config)

        # Simulate: existing DB where someone manually changed role to 'requester'
        with connect(app_config) as conn:
            conn.execute(
                "insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
                "values ('U-V2SE7PP', 'V2SE7PP', 'Li, Xingchen', 'requester', 'test@test.com', 'active', '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00')"
            )
            conn.commit()

        seed_users(app_config)

        with connect(app_config) as conn:
            user = conn.execute("select * from users where machine_id = 'V2SE7PP'").fetchone()
        # Role should stay as manually-set 'requester', not be reset to SEED_USERS 'admin'
        assert user["role"] == "requester"
