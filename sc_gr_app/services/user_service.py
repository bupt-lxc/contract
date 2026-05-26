from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import PermissionDenied


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


def get_user_by_machine_id(config: AppConfig, machine_id: str) -> dict:
    with connect(config) as conn:
        row = conn.execute(
            "select * from users where machine_id = ? and status = 'active'",
            (machine_id,),
        ).fetchone()

    if row is None:
        raise PermissionDenied("This machine is not authorized")
    return dict(row)
