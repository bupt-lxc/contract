from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import NotFound, PermissionDenied, ValidationError
from sc_gr_app.services.audit_service import write_audit_log


SEED_USERS = [
    ("V2SE7PP", "Li, Xingchen (C/EV-L)", "requester", "xingchen.li@audi.com.cn"),
    ("UJWVFIH", "Su, Tong (C/EV-L)", "requester", "tong.su@audi.com.cn"),
    ("EYANQM0", "Yang, Qiaomin (C/EV-L)", "admin", "qiaomin.yang@audi.com.cn"),
    ("FO5LZ6P", "Ye, Xiaorui (C/EV-L)", "requester", "xiaorui.ye@audi.com.cn"),
    ("EZHOLW0", "Zhou, Liwei (C/EV-L)", "requester", "liwei.zhou@audi.com.cn"),
    ("FPBTMS5", "Sun, Jialing (C/EV-L)", "admin", "jialing.sun@audi.com.cn"),
]


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def seed_users(config: AppConfig) -> None:
    timestamp = now()
    with connect(config) as conn:
        for machine_id, user_name, role, email in SEED_USERS:
            existing = conn.execute(
                "select user_id from users where machine_id = ?",
                (machine_id,),
            ).fetchone()
            if existing:
                continue
            conn.execute(
                """
                insert into users (
                  user_id, machine_id, user_name, role, email, status, created_at, updated_at
                ) values (?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (f"U-{machine_id}", machine_id, user_name, role, email, timestamp, timestamp),
            )
        conn.commit()


def list_active_users(config: AppConfig) -> list[dict]:
    with connect(config) as conn:
        rows = conn.execute(
            "select user_id, machine_id, user_name, role, email, status from users where status = 'active' order by user_name"
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_by_machine_id(config: AppConfig, machine_id: str) -> dict:
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()

    if row is None:
        raise PermissionDenied("This machine is not authorized")
    return dict(row)


def create_user(config: AppConfig, current_user: dict, data: dict) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can create users")
    machine_id = data["machine_id"]
    user_name = data["user_name"]
    email = data.get("email")
    role = data["role"]
    if role not in ("admin", "requester"):
        raise ValidationError("role must be 'admin' or 'requester'")
    user_id = f"U-{machine_id}"
    timestamp = now()
    with connect(config) as conn:
        existing = conn.execute(
            "select user_id from users where machine_id = ?",
            (machine_id,),
        ).fetchone()
        if existing:
            raise ValidationError(f"User with machine_id {machine_id} already exists")
        conn.execute(
            """
            insert into users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
            values (?, ?, ?, ?, ?, 'active', ?, ?)
            """,
            (user_id, machine_id, user_name, role, email, timestamp, timestamp),
        )
        write_audit_log(
            conn,
            action_type="create_user",
            object_type="user",
            object_id=user_id,
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=None,
            after={"user_id": user_id, "machine_id": machine_id, "user_name": user_name, "role": role, "email": email},
        )
        conn.commit()
    return {"user_id": user_id, "machine_id": machine_id, "user_name": user_name, "role": role, "email": email, "status": "active"}


def update_user(config: AppConfig, current_user: dict, machine_id: str, data: dict) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can update users")
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()
        if not row:
            raise NotFound(f"User with machine_id {machine_id} not found")
        before = dict(row)
        user_name = data.get("user_name", before["user_name"])
        email = data.get("email", before.get("email"))
        role = data.get("role", before["role"])
        if role not in ("admin", "requester"):
            raise ValidationError("role must be 'admin' or 'requester'")
        timestamp = now()
        conn.execute(
            "update users set user_name = ?, email = ?, role = ?, updated_at = ? where machine_id = ?",
            (user_name, email, role, timestamp, machine_id),
        )
        after = {**before, "user_name": user_name, "email": email, "role": role, "updated_at": timestamp}
        write_audit_log(
            conn,
            action_type="update_user",
            object_type="user",
            object_id=before["user_id"],
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=before,
            after=after,
        )
        conn.commit()
    return after


def disable_user(config: AppConfig, current_user: dict, machine_id: str) -> dict:
    if current_user.get("role") != "admin":
        raise PermissionDenied("Only admins can disable users")
    if machine_id == current_user.get("machine_id"):
        raise ValidationError("Cannot disable your own account")
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()
        if not row:
            raise NotFound(f"User with machine_id {machine_id} not found")
        before = dict(row)
        timestamp = now()
        conn.execute(
            "update users set status = 'disabled', updated_at = ? where machine_id = ?",
            (timestamp, machine_id),
        )
        after = {**before, "status": "disabled", "updated_at": timestamp}
        write_audit_log(
            conn,
            action_type="disable_user",
            object_type="user",
            object_id=before["user_id"],
            sc_id=None,
            operator_id=current_user["user_id"],
            machine_id=current_user["machine_id"],
            before=before,
            after=after,
        )
        conn.commit()
    return after
