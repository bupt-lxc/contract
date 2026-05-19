from datetime import datetime, timezone
from decimal import Decimal

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services.budget_service import (
    compute_po_budget_decimal,
    compute_sc_budget_decimal,
)
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("gr_id", "po_id", "estimated_amount")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def _validate_gr_creation_context(
    config: AppConfig,
    po_sc,
    amount: Decimal,
) -> None:
    if po_sc["sc_status"] != "approved":
        raise ConflictError("SC must be approved")
    if not po_sc["sc_no"]:
        raise ConflictError("SC No is required")
    if not po_sc["po_no"]:
        raise ConflictError("PO No is required")
    if po_sc["status"] != "po_approved":
        raise ConflictError("PO must be approved")
    sc_budget = compute_sc_budget_decimal(config, po_sc["sc_id"])
    po_budget = compute_po_budget_decimal(config, po_sc["po_id"])
    if sc_budget["sc_available_amount"] < amount:
        raise ConflictError("SC available amount is insufficient")
    if po_budget["open_po_amount"] < amount:
        raise ConflictError("PO open amount is insufficient")


def create_gr(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    estimated_amount = _positive_number(
        data["estimated_amount"],
        "estimated_amount",
    )
    po_id = data["po_id"]

    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            "select sc_id from pos where po_id = ?",
            (po_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"PO not found: {po_id}")
        sc_id = lookup["sc_id"]

    timestamp = utc_now()
    gr_id = data["gr_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
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
                      cancelled_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gr_id,
                        po_id,
                        current_user["user_id"],
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
                        approved_at = ?
                    where gr_id = ?
                    """,
                    (float(con_value_amount), current_user["user_id"], timestamp, gr_id),
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
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
