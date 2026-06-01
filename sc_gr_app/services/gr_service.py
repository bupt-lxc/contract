from datetime import datetime, timezone
from decimal import Decimal

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.rbac import require_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import (
    compute_po_budget_decimal,
    compute_sc_budget_decimal,
)
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("po_id", "requester_id", "estimated_amount")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_gr_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"GR-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT gr_id FROM gr_requests WHERE gr_id LIKE ? ORDER BY gr_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["gr_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"GR-{machine_id}-{today}-{seq:03d}"


def _require_fields(data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if data.get(field) in (None, ""):
            raise ValidationError(f"{field} is required")


def _positive_number(value, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValidationError(f"{field} must be positive") from None
    if not number.is_finite() or number <= 0:
        raise ValidationError(f"{field} must be positive")
    return number


def _non_negative_number(value, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except Exception:
        raise ValidationError(f"{field} must be non-negative") from None
    if not number.is_finite() or number < 0:
        raise ValidationError(f"{field} must be non-negative")
    return number


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_gr(conn, gr_id: str) -> dict:
    row = conn.execute(
        "select * from gr_requests where gr_id = ?",
        (gr_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"GR not found: {gr_id}")
    return _row_to_dict(row)


def _get_po_sc(conn, po_id: str):
    row = conn.execute(
        """
        select
          po.*,
          sc.sc_no,
          sc.status as sc_status,
          sc.sc_amount,
          vendor.vendor_name
        from pos po
        join sc_records sc on sc.sc_id = po.sc_id
        join vendors vendor on vendor.vendor_id = po.vendor_id
        where po.po_id = ?
        """,
        (po_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"PO not found: {po_id}")
    return row


def _get_gr_sc_id(conn, gr_id: str) -> str:
    lookup = conn.execute(
        """
        select po.sc_id
        from gr_requests gr
        join pos po on po.po_id = gr.po_id
        where gr.gr_id = ?
        """,
        (gr_id,),
    ).fetchone()
    if lookup is None:
        raise NotFound(f"GR not found: {gr_id}")
    return lookup["sc_id"]


def _require_editable_parent_sc(conn, sc_id: str) -> None:
    row = conn.execute(
        "select status from sc_records where sc_id = ?",
        (sc_id,),
    ).fetchone()
    if row is None:
        raise NotFound(f"SC not found: {sc_id}")
    if row["status"] == "closed":
        raise ConflictError("Closed SC cannot be edited")


def _validate_user_exists(conn, user_id: str) -> None:
    if user_id in (None, ""):
        raise ValidationError("requester_id is required")
    user = conn.execute(
        "select user_id from users where user_id = ?",
        (user_id,),
    ).fetchone()
    if user is None:
        raise NotFound(f"User not found: {user_id}")


def _validate_gr_creation_context(
    config: AppConfig,
    po_sc,
    amount: Decimal,
) -> None:
    if po_sc["sc_status"] != "approved":
        raise ConflictError("SC must be approved")
    if po_sc["status"] != "po_approved":
        raise ConflictError("PO must be approved")
    sc_budget = compute_sc_budget_decimal(config, po_sc["sc_id"])
    po_budget = compute_po_budget_decimal(config, po_sc["po_id"])
    if sc_budget["sc_available_amount"] < amount:
        raise ConflictError("SC available amount is insufficient")
    if po_budget["open_po_amount"] < amount:
        raise ConflictError("PO open amount is insufficient")


def create_gr(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    estimated_amount = _positive_number(
        data["estimated_amount"],
        "estimated_amount",
    )
    po_id = data["po_id"]
    requester_id = data["requester_id"]

    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            "select sc_id from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"PO not found: {po_id}")
        sc_id = lookup["sc_id"]

    timestamp = utc_now()

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        gr_id = _generate_gr_id(config, current_user["machine_id"])
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _validate_user_exists(conn, requester_id)
                po_sc = _get_po_sc(conn, po_id)
                _validate_gr_creation_context(config, po_sc, estimated_amount)
                conn.execute(
                    """
                    insert into gr_requests (
                      gr_id,
                      po_id,
                      requester_id,
                      estimated_amount,
                      con_value,
                      status,
                      remark,
                      created_by,
                      created_at,
                      approved_by,
                      approved_at,
                      cancelled_by,
                      cancelled_at,
                      pending_date,
                      approved_date
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gr_id,
                        po_id,
                        requester_id,
                        float(estimated_amount),
                        None,
                        "pending",
                        data.get("remark"),
                        current_user["user_id"],
                        timestamp,
                        None,
                        None,
                        None,
                        None,
                        timestamp,
                        None,
                    ),
                )
                created = _get_gr(conn, gr_id)
                write_audit_log(
                    conn,
                    action_type="create_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after=created,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (sc_id,),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "create",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def approve_gr(
    config: AppConfig,
    current_user: dict,
    gr_id: str,
    con_value,
) -> dict:
    require_admin(current_user)
    con_value_amount = _non_negative_number(con_value, "con_value")

    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            """
            select po.sc_id
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            where gr.gr_id = ?
            """,
            (gr_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"GR not found: {gr_id}")
        sc_id = lookup["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] != "pending":
                    raise ConflictError("GR must be pending")

                extra_amount = con_value_amount - Decimal(
                    str(before["estimated_amount"])
                )
                if extra_amount > 0:
                    sc_budget = compute_sc_budget_decimal(config, sc_id)
                    po_budget = compute_po_budget_decimal(config, before["po_id"])
                    if sc_budget["sc_available_amount"] < extra_amount:
                        raise ConflictError(
                            "SC available amount is insufficient"
                        )
                    if po_budget["open_po_amount"] < extra_amount:
                        raise ConflictError("PO open amount is insufficient")

                timestamp = utc_now()
                conn.execute(
                    """
                    update gr_requests
                    set status = 'approved',
                        con_value = ?,
                        approved_by = ?,
                        approved_at = ?,
                        approved_date = ?
                    where gr_id = ?
                    """,
                    (float(con_value_amount), current_user["user_id"], timestamp, timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_audit_log(
                    conn,
                    action_type="approve_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (sc_id,),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "approve",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def update_gr(
    config: AppConfig,
    current_user: dict,
    gr_id: str,
    data: dict,
) -> dict:
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] == "cancelled":
                    raise ConflictError("Cancelled GR cannot be edited")

                updates = dict(data)
                if before["status"] == "pending":
                    allowed = {
                        key: updates[key]
                        for key in (
                            "po_id",
                            "requester_id",
                            "estimated_amount",
                            "remark",
                            "pending_date",
                            "approved_date",
                        )
                        if key in updates
                    }
                    if not allowed:
                        raise ValidationError("No GR fields to update")

                    merged = {**before, **allowed}
                    if "requester_id" in allowed:
                        _validate_user_exists(conn, merged["requester_id"])
                    amount = _positive_number(
                        merged["estimated_amount"],
                        "estimated_amount",
                    )
                    po_sc = _get_po_sc(conn, merged["po_id"])
                    if po_sc["sc_status"] != "approved":
                        raise ConflictError("SC must be approved")
                    if po_sc["status"] != "po_approved":
                        raise ConflictError("PO must be approved")

                    old_amount = Decimal(str(before["estimated_amount"]))
                    if po_sc["sc_id"] == sc_id:
                        sc_budget_amount = amount - old_amount
                    else:
                        sc_budget_amount = amount
                    if sc_budget_amount > 0:
                        sc_budget = compute_sc_budget_decimal(config, po_sc["sc_id"])
                        if sc_budget["sc_available_amount"] < sc_budget_amount:
                            raise ConflictError(
                                "SC available amount is insufficient"
                            )

                    if merged["po_id"] == before["po_id"]:
                        po_budget_amount = amount - old_amount
                    else:
                        po_budget_amount = amount
                    if po_budget_amount > 0:
                        po_budget = compute_po_budget_decimal(config, merged["po_id"])
                        if po_budget["open_po_amount"] < po_budget_amount:
                            raise ConflictError("PO open amount is insufficient")

                    conn.execute(
                        """
                        update gr_requests
                        set po_id = ?,
                            requester_id = ?,
                            estimated_amount = ?,
                            remark = ?,
                            pending_date = ?,
                            approved_date = ?
                        where gr_id = ?
                        """,
                        (
                            merged["po_id"],
                            merged["requester_id"],
                            float(amount),
                            merged.get("remark"),
                            merged.get("pending_date"),
                            merged.get("approved_date"),
                            gr_id,
                        ),
                    )
                else:
                    allowed = {
                        key: updates[key]
                        for key in ("con_value", "remark")
                        if key in updates
                    }
                    if not allowed:
                        raise ValidationError("No GR fields to update")

                    merged = {**before, **allowed}
                    if merged.get("con_value") is None:
                        raise ValidationError("con_value is required for approved GR")
                    con_value = _non_negative_number(
                        merged["con_value"],
                        "con_value",
                    )
                    extra_amount = con_value - Decimal(str(before["con_value"]))
                    if extra_amount > 0:
                        sc_budget = compute_sc_budget_decimal(config, sc_id)
                        po_budget = compute_po_budget_decimal(config, before["po_id"])
                        if sc_budget["sc_available_amount"] < extra_amount:
                            raise ConflictError(
                                "SC available amount is insufficient"
                            )
                        if po_budget["open_po_amount"] < extra_amount:
                            raise ConflictError("PO open amount is insufficient")

                    conn.execute(
                        """
                        update gr_requests
                        set con_value = ?,
                            remark = ?
                        where gr_id = ?
                        """,
                        (float(con_value), merged.get("remark"), gr_id),
                    )

                after = _get_gr(conn, gr_id)
                audit_sc_ids = [sc_id]
                if before["status"] == "pending" and after["po_id"] != before["po_id"]:
                    after_sc_id = _get_po_sc(conn, after["po_id"])["sc_id"]
                    if after_sc_id != sc_id:
                        audit_sc_ids.append(after_sc_id)
                for audit_sc_id in audit_sc_ids:
                    write_audit_log(
                        conn,
                        action_type="update_gr",
                        object_type="gr",
                        object_id=gr_id,
                        sc_id=audit_sc_id,
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


def cancel_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] != "pending":
                    raise ConflictError("GR must be pending")

                timestamp = utc_now()
                conn.execute(
                    """
                    update gr_requests
                    set status = 'cancelled',
                        cancelled_by = ?,
                        cancelled_at = ?
                    where gr_id = ?
                    """,
                    (current_user["user_id"], timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_audit_log(
                    conn,
                    action_type="cancel_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (sc_id,),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "cancel",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
