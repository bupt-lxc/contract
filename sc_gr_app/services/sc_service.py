from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import (
    compute_po_budget,
    compute_sc_budget,
)
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
OPTIONAL_UPDATE_FIELDS = (
    "sc_no",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
    "description",
)
REQUIRED_BUSINESS_FIELDS = (
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
)


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
    if not isfinite(number) or number <= 0:
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


def _require_submit_fields(data: dict) -> None:
    _require_fields(data, REQUIRED_BUSINESS_FIELDS)
    if data["request_type"] not in SUPPORTED_REQUEST_TYPES:
        raise ValidationError("request_type is invalid")
    _positive_number(data["sc_amount"], "sc_amount")
    _validate_service_period(data)


def _assert_can_view_sc(user: dict, sc: dict) -> None:
    if sc["status"] == "draft":
        if user.get("role") != "requester" or user.get("user_id") != sc["requester_id"]:
            raise PermissionDenied("SC is not visible")
        return
    if user.get("role") == "admin":
        return
    if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
        return
    raise PermissionDenied("SC is not visible")


def _assert_can_edit_sc(user: dict, sc: dict) -> None:
    if sc["status"] == "draft":
        if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
            return
        raise PermissionDenied("Only the draft owner can edit this SC")
    if sc["status"] == "closed":
        raise ConflictError("Closed SC cannot be edited")
    if user.get("role") == "admin":
        return
    raise PermissionDenied("Admin permission required")


def _sc_permissions(user: dict, sc: dict) -> dict:
    is_admin = user.get("role") == "admin"
    is_owner = user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]
    is_draft = sc["status"] == "draft"
    is_pending = sc["status"] == "pending"
    is_approved = sc["status"] == "approved"
    is_closed = sc["status"] == "closed"
    return {
        "can_edit_sc": (is_owner and is_draft) or (is_admin and not is_draft and not is_closed),
        "can_submit_sc": is_owner and is_draft,
        "can_approve_sc": is_admin and is_pending and bool(sc.get("sc_no")),
        "can_deny_sc": is_admin and is_pending,
        "can_close_sc": is_admin and is_approved,
        "can_manage_po": is_admin and is_approved,
        "can_manage_gr": is_admin and is_approved,
    }


def _validate_service_period(data: dict) -> None:
    start = data.get("service_period_start")
    end = data.get("service_period_end")
    if start not in (None, "") and end not in (None, "") and start > end:
        raise ValidationError("service period is invalid")


def _require_non_draft_business_fields(sc: dict) -> None:
    if sc["status"] == "draft":
        return
    _require_fields(sc, REQUIRED_BUSINESS_FIELDS)


def _validate_sc_amount_not_below_usage(config: AppConfig, sc_id: str, sc_amount) -> None:
    amount = Decimal(str(sc_amount))
    with connect(config) as conn:
        po_amounts = [
            Decimal(str(row["po_amount"]))
            for row in conn.execute(
                "select po_amount from pos where sc_id = ?",
                (sc_id,),
            )
        ]
        gr_rows = conn.execute(
            """
            select gr.status, gr.estimated_amount, gr.con_value
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where po.sc_id = ?
              and gr.status in ('pending', 'approved')
            """,
            (sc_id,),
        ).fetchall()

    allocated_po_amount = sum(po_amounts, Decimal("0"))
    if amount < allocated_po_amount:
        raise ConflictError("SC amount cannot be below allocated PO amount")

    gr_usage = sum(
        (
            Decimal(str(row["estimated_amount"]))
            if row["status"] == "pending"
            else Decimal(str(row["con_value"]))
        )
        for row in gr_rows
    )
    if amount < gr_usage:
        raise ConflictError("SC amount cannot be below GR usage")


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


def create_sc_draft(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, ("sc_id", "requester_id"))
    if (
        current_user["role"] == "requester"
        and data["requester_id"] != current_user["user_id"]
    ):
        raise PermissionDenied("Requester can only create their own draft SC")

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
                        data.get("request_type"),
                        data.get("cost_center"),
                        (
                            float(data["sc_amount"])
                            if data.get("sc_amount") not in (None, "")
                            else None
                        ),
                        data.get("service_period_start"),
                        data.get("service_period_end"),
                        "draft",
                        data.get("description"),
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                        None,
                        None,
                        None,
                    ),
                )
                created = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="create_sc_draft",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
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


def submit_sc(config: AppConfig, current_user: dict, sc_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "draft":
                    raise ConflictError("SC must be draft")
                if (
                    current_user["role"] != "requester"
                    or before["requester_id"] != current_user["user_id"]
                ):
                    raise PermissionDenied("Only the draft owner can submit this SC")
                merged = {**before, **data}
                _require_submit_fields(merged)

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set sc_no = ?,
                        request_type = ?,
                        cost_center = ?,
                        sc_amount = ?,
                        service_period_start = ?,
                        service_period_end = ?,
                        description = ?,
                        status = 'pending',
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (
                        merged.get("sc_no"),
                        merged["request_type"],
                        merged["cost_center"],
                        float(merged["sc_amount"]),
                        merged["service_period_start"],
                        merged["service_period_end"],
                        merged.get("description"),
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="submit_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "submit", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def update_sc(config: AppConfig, current_user: dict, sc_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    allowed = {key: value for key, value in data.items() if key in OPTIONAL_UPDATE_FIELDS}
    if not allowed:
        raise ValidationError("No SC fields to update")

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                _assert_can_edit_sc(current_user, before)
                merged = {**before, **allowed}
                _require_non_draft_business_fields(merged)
                if (
                    merged.get("request_type") not in (None, "")
                    and merged["request_type"] not in SUPPORTED_REQUEST_TYPES
                ):
                    raise ValidationError("request_type is invalid")
                if merged.get("sc_amount") not in (None, ""):
                    _positive_number(merged["sc_amount"], "sc_amount")
                _validate_service_period(merged)
                if "sc_amount" in allowed and merged.get("sc_amount") not in (None, ""):
                    _validate_sc_amount_not_below_usage(
                        config,
                        sc_id,
                        merged["sc_amount"],
                    )

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set sc_no = ?,
                        request_type = ?,
                        cost_center = ?,
                        sc_amount = ?,
                        service_period_start = ?,
                        service_period_end = ?,
                        description = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (
                        merged.get("sc_no"),
                        merged.get("request_type"),
                        merged.get("cost_center"),
                        (
                            float(merged["sc_amount"])
                            if merged.get("sc_amount") not in (None, "")
                            else None
                        ),
                        merged.get("service_period_start"),
                        merged.get("service_period_end"),
                        merged.get("description"),
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="update_sc",
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


def deny_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
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
                    set status = 'denied',
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="deny_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "deny", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def close_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "approved":
                    raise ConflictError("SC must be approved")

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set status = 'closed',
                        closed_at = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_audit_log(
                    conn,
                    action_type="close_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "close", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def get_sc_detail(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    with connect(config) as conn:
        sc = _get_sc(conn, sc_id)
        _assert_can_view_sc(current_user, sc)
        pos = [
            _row_to_dict(row)
            for row in conn.execute(
                "select * from pos where sc_id = ? order by created_at, po_id",
                (sc_id,),
            )
        ]
        grs = [
            _row_to_dict(row)
            for row in conn.execute(
                """
                select gr.*
                from gr_requests gr
                join pos po on po.po_id = gr.po_id
                where po.sc_id = ?
                order by gr.created_at, gr.gr_id
                """,
                (sc_id,),
            )
        ]
        audit_logs = [
            _row_to_dict(row)
            for row in conn.execute(
                """
                select *
                from audit_logs
                where sc_id = ?
                order by created_at desc
                """,
                (sc_id,),
            )
        ]

    for po in pos:
        po["budget"] = compute_po_budget(config, po["po_id"])
        po["open_po_amount"] = po["budget"]["open_po_amount"]

    return {
        "sc": sc,
        "budget": compute_sc_budget(config, sc_id),
        "pos": pos,
        "grs": grs,
        "audit_logs": audit_logs,
        "permissions": _sc_permissions(current_user, sc),
    }


def approve_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "pending":
                    raise ConflictError("SC must be pending")
                if not before["sc_no"]:
                    raise ConflictError("SC No is required")

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
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "approve", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
