from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import PermissionDenied
from sc_gr_app.identity import get_7_digit_id


DEFAULT_ADMIN_USER_ID = "U-ADMIN"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_default_admin(config: AppConfig) -> None:
    machine_id = get_7_digit_id()
    if not machine_id:
        raise PermissionDenied("Failed to get Windows user ID")

    with connect(config) as conn:
        existing = conn.execute(
            "select user_id from users where machine_id = ?",
            (machine_id,),
        ).fetchone()
        if existing:
            return

        existing_default_admin = conn.execute(
            "select user_id from users where user_id = ?",
            (DEFAULT_ADMIN_USER_ID,),
        ).fetchone()
        if existing_default_admin:
            return

        timestamp = now()
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
                DEFAULT_ADMIN_USER_ID,
                machine_id,
                "Default Admin",
                "admin",
                None,
                "active",
                timestamp,
                timestamp,
            ),
        )
        conn.commit()


def get_user_by_machine_id(config: AppConfig, machine_id: str) -> dict:
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()

    if row is None:
        raise PermissionDenied("This machine is not authorized")
    return dict(row)
