from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.rbac import require_requester_or_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("vendor_id", "vendor_name", "service_scope")
SUPPORTED_SERVICE_SCOPES = {
    "Transportation",
    "engineering Service",
    "Equipment",
    "Parts",
    "Driver",
    "Test car rental",
    "General Service",
    "Dealers",
    "Import&Export&cusoms clearance",
    "Insurance",
    "Harness",
    "Maintenance",
    "Security",
    "Testing support",
    "Others",
}
OPTIONAL_FIELDS = (
    "ksrm_vendor_code",
    "contact_person",
    "phone",
    "email",
    "description",
    "inquiry_history",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_fields(data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if data.get(field) in (None, ""):
            raise ValidationError(f"{field} is required")


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_vendor(conn, vendor_id: str) -> dict:
    return _row_to_dict(
        conn.execute(
            "select * from vendors where vendor_id = ?",
            (vendor_id,),
        ).fetchone()
    )


def create_vendor(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    if data["service_scope"] not in SUPPORTED_SERVICE_SCOPES:
        raise ValidationError("service_scope is invalid")

    timestamp = utc_now()
    vendor_id = data["vendor_id"]

    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    insert into vendors (
                      vendor_id,
                      vendor_name,
                      ksrm_vendor_code,
                      contact_person,
                      phone,
                      service_scope,
                      email,
                      description,
                      inquiry_history,
                      created_by,
                      created_at,
                      updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vendor_id,
                        data["vendor_name"],
                        data.get("ksrm_vendor_code"),
                        data.get("contact_person"),
                        data.get("phone"),
                        data["service_scope"],
                        data.get("email"),
                        data.get("description"),
                        data.get("inquiry_history"),
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                    ),
                )
                created = _get_vendor(conn, vendor_id)
                write_audit_log(
                    conn,
                    action_type="create_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after=created,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def search_vendors(config: AppConfig, text: str | None = None) -> list[dict]:
    with connect(config) as conn:
        if text:
            like_text = f"%{text.lower()}%"
            rows = conn.execute(
                """
                select *
                from vendors
                where lower(vendor_name) like ?
                   or lower(coalesce(ksrm_vendor_code, '')) like ?
                order by vendor_name asc
                """,
                (like_text, like_text),
            ).fetchall()
        else:
            rows = conn.execute(
                "select * from vendors order by vendor_name asc"
            ).fetchall()

    return [_row_to_dict(row) for row in rows]
