from datetime import datetime, timezone
from decimal import Decimal

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.rbac import require_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import compute_sc_budget_decimal
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("sc_id", "vendor_id", "po_amount")
SUPPORTED_STATUSES = {"po_pending", "po_approved", "finished"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_po_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"PO-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT po_id FROM pos WHERE po_id LIKE ? ORDER BY po_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["po_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"PO-{machine_id}-{today}-{seq:03d}"


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


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_po(conn, po_id: str) -> dict:
    return _row_to_dict(
        conn.execute("select * from pos where po_id = ?", (po_id,)).fetchone()
    )


def _get_po_or_raise(conn, po_id: str) -> dict:
    row = conn.execute("select * from pos where po_id = ?", (po_id,)).fetchone()
    if row is None:
        raise NotFound(f"PO not found: {po_id}")
    return _row_to_dict(row)


def _po_gr_usage(conn, po_id: str) -> Decimal:
    null_con_value_gr = conn.execute(
        """
        select gr_id
        from gr_requests
        where po_id = ?
          and status = 'approved'
          and con_value is null
        limit 1
        """,
        (po_id,),
    ).fetchone()
    if null_con_value_gr is not None:
        raise ConflictError(
            f"Approved GR has NULL con_value for PO {po_id}: "
            f"{null_con_value_gr['gr_id']}"
        )

    usage = Decimal("0")
    rows = conn.execute(
        """
        select status, estimated_amount, con_value
        from gr_requests
        where po_id = ?
          and status in ('pending', 'approved')
        """,
        (po_id,),
    )
    for row in rows:
        if row["status"] == "pending":
            usage += Decimal(str(row["estimated_amount"]))
        else:
            usage += Decimal(str(row["con_value"]))
    return usage


def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    po_amount = _positive_number(data["po_amount"], "po_amount")
    status = data.get("status", "po_pending")
    if status not in SUPPORTED_STATUSES:
        raise ValidationError("status is invalid")

    sc_id = data["sc_id"]
    po_id = _generate_po_id(config, current_user["machine_id"])
    timestamp = utc_now()

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                sc = conn.execute(
                    "select * from sc_records where sc_id = ?",
                    (sc_id,),
                ).fetchone()
                if sc is None:
                    raise NotFound(f"SC not found: {sc_id}")
                if sc["status"] != "approved":
                    raise ConflictError("SC must be approved")

                vendor = conn.execute(
                    "select vendor_id from vendors where vendor_id = ?",
                    (data["vendor_id"],),
                ).fetchone()
                if vendor is None:
                    raise NotFound(f"Vendor not found: {data['vendor_id']}")

                budget = compute_sc_budget_decimal(config, sc_id)
                if budget["allocated_po_amount"] + po_amount > Decimal(
                    str(sc["sc_amount"])
                ):
                    raise ConflictError("PO total would exceed SC amount")

                conn.execute(
                    """
                    insert into pos (
                      po_id,
                      sc_id,
                      vendor_id,
                      po_no,
                      po_amount,
                      status,
                      contract_from,
                      contract_to,
                      contract_no,
                      payment_frequency,
                      created_at,
                      updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        po_id,
                        sc_id,
                        data["vendor_id"],
                        data.get("po_no"),
                        float(po_amount),
                        status,
                        data.get("contract_from"),
                        data.get("contract_to"),
                        data.get("contract_no"),
                        data.get("payment_frequency"),
                        timestamp,
                        timestamp,
                    ),
                )
                created = _get_po(conn, po_id)
                write_audit_log(
                    conn,
                    action_type="create_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after=created,
                )
                notification_service.queue_status_change(
                    conn, "po", po_id, "create",
                    {"requester_id": sc["requester_id"]}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def update_po(config: AppConfig, current_user: dict, po_id: str, data: dict) -> dict:
    require_admin(current_user)
    allowed_fields = {
        "vendor_id",
        "po_no",
        "po_amount",
        "contract_from",
        "contract_to",
        "contract_no",
        "payment_frequency",
    }
    updates = {key: value for key, value in data.items() if key in allowed_fields}
    if not updates:
        raise ValidationError("No PO fields to update")

    with connect(config) as lookup_conn:
        sc_id = _get_po_or_raise(lookup_conn, po_id)["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                sc = conn.execute(
                    "select * from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if sc["status"] == "closed":
                    raise ConflictError("Closed SC cannot be edited")

                merged = {**before, **updates}
                po_amount = _positive_number(merged["po_amount"], "po_amount")
                if po_amount < _po_gr_usage(conn, po_id):
                    raise ConflictError("PO amount cannot be below GR usage")

                if merged["vendor_id"] != before["vendor_id"]:
                    vendor = conn.execute(
                        "select vendor_id from vendors where vendor_id = ?",
                        (merged["vendor_id"],),
                    ).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {merged['vendor_id']}")

                sibling_total = sum(
                    (
                        Decimal(str(row["po_amount"]))
                        for row in conn.execute(
                            "select po_amount from pos where sc_id = ? and po_id != ?",
                            (before["sc_id"], po_id),
                        )
                    ),
                    Decimal("0"),
                )
                if sibling_total + po_amount > Decimal(str(sc["sc_amount"])):
                    raise ConflictError("PO total would exceed SC amount")

                timestamp = utc_now()
                conn.execute(
                    """
                    update pos
                    set vendor_id = ?,
                        po_no = ?,
                        po_amount = ?,
                        contract_from = ?,
                        contract_to = ?,
                        contract_no = ?,
                        payment_frequency = ?,
                        updated_at = ?
                    where po_id = ?
                    """,
                    (
                        merged["vendor_id"],
                        merged.get("po_no"),
                        float(po_amount),
                        merged.get("contract_from"),
                        merged.get("contract_to"),
                        merged.get("contract_no"),
                        merged.get("payment_frequency"),
                        timestamp,
                        po_id,
                    ),
                )
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(
                    conn,
                    action_type="update_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=before["sc_id"],
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


def approve_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_po_or_raise(lookup_conn, po_id)["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                sc = conn.execute(
                    "select status from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if sc["status"] == "closed":
                    raise ConflictError("Closed SC cannot be edited")
                if before["status"] != "po_pending":
                    raise ConflictError("PO must be pending")

                timestamp = utc_now()
                conn.execute(
                    """
                    update pos
                    set status = 'po_approved',
                        updated_at = ?
                    where po_id = ?
                    """,
                    (timestamp, po_id),
                )
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(
                    conn,
                    action_type="approve_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=before["sc_id"],
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "po", po_id, "approve",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_po_or_raise(lookup_conn, po_id)["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                sc = conn.execute(
                    "select status from sc_records where sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if sc["status"] == "closed":
                    raise ConflictError("Closed SC cannot be edited")
                if before["status"] != "po_approved":
                    raise ConflictError("PO must be approved")

                timestamp = utc_now()
                conn.execute(
                    """
                    update pos
                    set status = 'finished',
                        updated_at = ?
                    where po_id = ?
                    """,
                    (timestamp, po_id),
                )
                after = _get_po_or_raise(conn, po_id)
                write_audit_log(
                    conn,
                    action_type="finish_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=before["sc_id"],
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "po", po_id, "finish",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after
