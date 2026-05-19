from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = (
    "sc_id",
    "requester_id",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
)
SUPPORTED_REQUEST_TYPES = {"material", "service", "fixed_asset", "FC"}
SUPPORTED_STATUSES = {"pending", "approved", "denied", "closed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_fields(data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if data.get(field) in (None, ""):
            raise ValidationError(f"{field} is required")


def _positive_number(value, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise ValidationError(f"{field} must be positive") from None
    if number <= 0:
        raise ValidationError(f"{field} must be positive")
    return number


def _row_to_dict(row) -> dict:
    return dict(row)


def _fetch_sc(conn, sc_id: str):
    return conn.execute(
        "select * from sc_records where sc_id = ?",
        (sc_id,),
    ).fetchone()


def _get_sc(conn, sc_id: str) -> dict:
    row = _fetch_sc(conn, sc_id)
    if row is None:
        raise NotFound(f"SC not found: {sc_id}")
    return _row_to_dict(row)


def create_sc(
    config: AppConfig,
    current_user: dict,
    data: dict,
    operation_mode: str = "normal",
) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    if data["request_type"] not in SUPPORTED_REQUEST_TYPES:
        raise ValidationError("request_type is invalid")
    sc_amount = _positive_number(data["sc_amount"], "sc_amount")

    if operation_mode == "normal":
        status = "pending"
    elif operation_mode == "backfill":
        require_admin(current_user)
        status = data.get("status", "pending")
        if status not in SUPPORTED_STATUSES:
            raise ValidationError("status is invalid")
    else:
        raise ValidationError("operation_mode is invalid")

    timestamp = utc_now()
    sc_id = data["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    insert into sc_records (
                      sc_id,
                      sc_no,
                      requester_id,
                      request_type,
                      cost_center,
                      sc_amount,
                      service_period_start,
                      service_period_end,
                      status,
                      description,
                      created_by,
                      created_at,
                      updated_at,
                      approved_by,
                      approved_at,
                      closed_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sc_id,
                        data.get("sc_no"),
                        data["requester_id"],
                        data["request_type"],
                        data["cost_center"],
                        sc_amount,
                        data["service_period_start"],
                        data["service_period_end"],
                        status,
                        data.get("description"),
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                        current_user["user_id"] if status == "approved" else None,
                        timestamp if status == "approved" else None,
                        timestamp if status == "closed" else None,
                    ),
                )
                created = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="create_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after=created,
                    operation_mode=operation_mode,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def approve_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "pending":
                    raise ConflictError("SC must be pending")

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set status = 'approved',
                        approved_by = ?,
                        approved_at = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (current_user["user_id"], timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="approve_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
