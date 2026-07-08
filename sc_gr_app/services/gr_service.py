from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.record_service import write_operation_record
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import (
    compute_po_budget_decimal,
    compute_sc_budget_decimal,
)
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("po_id", "requester_id", "estimated_amount")
SUPPORTED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "finished"}


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
    if row["status"] == "finished":
        raise ConflictError("Finished SC cannot be edited")


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
    gr_status: str = "pending",
) -> None:
    """Validate that a GR can be created in the given PO/SC context.

    - draft PO under draft SC → only draft GR allowed, no budget check
    - active PO under approved SC → only pending / manager_confirm GR allowed, full budget check
    - other combinations → rejected
    """
    sc_status = po_sc["sc_status"]
    po_status = po_sc["status"]

    if po_status == "draft" and sc_status == "draft":
        if gr_status != "draft":
            raise ConflictError("Draft PO only allows draft GR")
        return  # no budget check for draft

    if po_status == "active" and sc_status == "approved":
        if gr_status not in ("draft", "pending", "manager_confirm"):
            raise ConflictError("Active PO only allows draft, pending or manager_confirm GR")
        sc_budget = compute_sc_budget_decimal(config, po_sc["sc_id"])
        po_budget = compute_po_budget_decimal(config, po_sc["po_id"])
        if sc_budget["sc_available_amount"] < amount:
            raise ConflictError("SC available amount is insufficient")
        if po_budget["open_po_amount"] < amount:
            raise ConflictError("PO open amount is insufficient")
        return

    raise ConflictError("SC must be draft or approved to add GR")


def create_gr(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    estimated_amount = _positive_number(
        data["estimated_amount"],
        "estimated_amount",
    )
    po_id = data["po_id"]
    requester_id = data["requester_id"]

    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            "select pos.sc_id, sc.requester_id as sc_requester "
            "from pos join sc_records sc on sc.sc_id = pos.sc_id "
            "where pos.po_id = ?",
            (po_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"PO not found: {po_id}")
        sc_id = lookup["sc_id"]
        if current_user["role"] != "admin" and lookup["sc_requester"] != current_user["user_id"]:
            raise PermissionDenied("Only the SC owner or admin can create GRs")

    timestamp = utc_now()

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        gr_id = _generate_gr_id(config, current_user["machine_id"])
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _validate_user_exists(conn, requester_id)
                po_sc = _get_po_sc(conn, po_id)

                # Derive GR status from PO/SC context
                gr_status = data.get("status")
                if gr_status is None:
                    gr_status = "draft" if po_sc["status"] == "draft" else "pending"
                elif gr_status not in SUPPORTED_STATUSES:
                    raise ValidationError(f"Invalid GR status: {gr_status}")

                _validate_gr_creation_context(config, po_sc, estimated_amount, gr_status)

                is_draft = gr_status == "draft"
                gross_cost = _compute_incl_tax(estimated_amount, data.get("tax_rate"))
                conn.execute(
                    """
                    insert into gr_requests (
                      gr_id,
                      gr_no,
                      po_id,
                      requester_id,
                      estimated_amount,
                      con_value,
                      gross_cost,
                      tax_rate,
                      status,
                      remark,
                      created_by,
                      created_at,
                      approved_by,
                      approved_at,
                      denied_by,
                      denied_at,
                      pending_date,
                      approved_date,
                      goods_service_description,
                      confirmation_name,
                      delivery_from,
                      delivery_to,
                      last_delivery
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        gr_id,
                        data.get("gr_no"),
                        po_id,
                        requester_id,
                        float(estimated_amount),
                        None,
                        float(gross_cost) if gross_cost is not None else None,
                        data.get("tax_rate"),
                        gr_status,
                        data.get("remark"),
                        current_user["user_id"],
                        timestamp,
                        None,
                        None,
                        None,
                        None,
                        None if is_draft else timestamp,
                        None,
                        data.get("goods_service_description"),
                        data.get("confirmation_name"),
                        data.get("delivery_from"),
                        data.get("delivery_to"),
                        data.get("last_delivery"),
                    ),
                )
                created = _get_gr(conn, gr_id)
                write_operation_record(
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
                if not is_draft:
                    notification_service.queue_status_change(
                        conn, "gr", gr_id, "submit",
                        {"requester_id": sc["requester_id"]} if sc else {}, current_user
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def _submit_gr_drafts(conn, gr_ids: list[str], timestamp: str) -> list[dict]:
    """Submit draft GRs in-place on an existing connection (no lock acquisition).

    Used internally by approve_po for cascade submission.
    Returns list of submitted GR dicts.
    """
    submitted = []
    for gr_id in gr_ids:
        before = _get_gr(conn, gr_id)
        if before["status"] != "draft":
            raise ConflictError(f"GR must be draft to submit: {gr_id}")

        conn.execute(
            """
            update gr_requests
            set status = 'manager_confirm',
                submitted_date = ?,
                pending_date = ?
            where gr_id = ?
            """,
            (timestamp, timestamp, gr_id),
        )
        after = _get_gr(conn, gr_id)

        # Resolve sc_id for audit
        po_sc = conn.execute(
            "select sc_id from pos where po_id = ?",
            (after["po_id"],),
        ).fetchone()
        sc_id = po_sc["sc_id"] if po_sc else None

        write_operation_record(
            conn,
            action_type="submit_gr",
            object_type="gr",
            object_id=gr_id,
            sc_id=sc_id,
            operator_id=after["created_by"],
            machine_id="SYSTEM_CASCADE",
            before=before,
            after=after,
        )
        sc = conn.execute(
            "SELECT requester_id FROM sc_records WHERE sc_id = ?",
            (sc_id,),
        ).fetchone()
        notification_service.queue_status_change(
            conn, "gr", gr_id, "submit",
            {"requester_id": sc["requester_id"]} if sc else {}, {"user_id": after["created_by"], "machine_id": "SYSTEM_CASCADE"}
        )
        submitted.append(after)
    return submitted


def _cascade_approve_grs(conn, gr_ids: list[str], current_user_id: str, timestamp: str) -> list[dict]:
    """Approve pending GRs in-place on an existing connection (no lock acquisition).

    Used internally by approve_po for cascade approval.
    Uses gross_cost as con_value, falling back to estimated_amount.
    Returns list of approved GR dicts.
    """
    approved = []
    for gr_id in gr_ids:
        before = _get_gr(conn, gr_id)
        if before["status"] != "pending":
            raise ConflictError(f"GR must be pending to approve: {gr_id}")

        con_value = before.get("gross_cost") or before["estimated_amount"]
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
            (con_value, current_user_id, timestamp, timestamp, gr_id),
        )
        after = _get_gr(conn, gr_id)

        po_sc = conn.execute(
            "select sc_id from pos where po_id = ?",
            (after["po_id"],),
        ).fetchone()
        sc_id = po_sc["sc_id"] if po_sc else None

        write_operation_record(
            conn,
            action_type="approve_gr",
            object_type="gr",
            object_id=gr_id,
            sc_id=sc_id,
            operator_id=current_user_id,
            machine_id="SYSTEM_CASCADE",
            before=before,
            after=after,
        )
        sc = conn.execute(
            "SELECT requester_id FROM sc_records WHERE sc_id = ?",
            (sc_id,),
        ).fetchone()
        notification_service.queue_status_change(
            conn, "gr", gr_id, "approve",
            {"requester_id": sc["requester_id"]} if sc else {},
            {"user_id": current_user_id, "machine_id": "SYSTEM_CASCADE"}
        )
        approved.append(after)
    return approved


def submit_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    """Manually submit a draft GR to manager_confirm status (with budget check)."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_gr(conn, gr_id)
                if before["status"] != "draft":
                    raise ConflictError("GR must be draft to submit")

                # PO must be approved before submitting GR
                po = conn.execute(
                    "SELECT status FROM pos WHERE po_id = ?",
                    (before["po_id"],),
                ).fetchone()
                if po is None:
                    raise ConflictError("PO not found")
                if po["status"] != "active":
                    raise ConflictError("PO must be active before submitting GR")

                # Budget check at submission time
                estimated_amount = Decimal(str(before["estimated_amount"] or 0))
                sc_budget = compute_sc_budget_decimal(config, sc_id)
                po_budget = compute_po_budget_decimal(config, before["po_id"])
                if sc_budget["sc_available_amount"] < estimated_amount:
                    raise ConflictError("SC available amount is insufficient")
                if po_budget["open_po_amount"] < estimated_amount:
                    raise ConflictError("PO open amount is insufficient")

                timestamp = utc_now()
                _submit_gr_drafts(conn, [gr_id], timestamp)
                after = _get_gr(conn, gr_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def confirm_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    """Admin confirms a GR in manager_confirm status, moving it to pending."""
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_gr(conn, gr_id)
                if before["status"] != "manager_confirm":
                    raise ConflictError("GR must be in manager_confirm status")

                timestamp = utc_now()
                conn.execute(
                    """
                    update gr_requests
                    set status = 'pending',
                        confirmed_at = ?,
                        pending_date = ?
                    where gr_id = ?
                    """,
                    (timestamp, timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_operation_record(
                    conn,
                    action_type="confirm_gr",
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
                    conn, "gr", gr_id, "confirm",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def _compute_incl_tax(estimated_amount: Decimal, tax_rate) -> Decimal:
    """Calculate tax-included amount: amount_ex_tax × (1 + tax_rate/100).

    Returns estimated_amount when tax_rate is None (gross = net).
    """
    if tax_rate is None:
        return estimated_amount
    rate = Decimal(str(tax_rate))
    return estimated_amount * (1 + rate / Decimal("100"))


def approve_gr(
    config: AppConfig,
    current_user: dict,
    gr_id: str,
    con_value=None,
) -> dict:
    require_admin(current_user)

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

                # Resolve con_value: explicit value → auto-fill from gross_cost
                if con_value is not None:
                    con_value_amount = _non_negative_number(con_value, "con_value")
                elif before.get("gross_cost") is not None:
                    con_value_amount = Decimal(str(before["gross_cost"]))
                else:
                    raise ValidationError(
                        "con_value is required (no gross_cost available for auto-fill)"
                    )

                extra_amount = con_value_amount - Decimal(
                    str(before["estimated_amount"] or 0)
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
                write_operation_record(
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
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        lookup = lookup_conn.execute(
            """
            select po.sc_id, sc.requester_id as sc_requester
            from gr_requests gr
            join pos po on po.po_id = gr.po_id
            join sc_records sc on sc.sc_id = po.sc_id
            where gr.gr_id = ?
            """,
            (gr_id,),
        ).fetchone()
        if lookup is None:
            raise NotFound(f"GR not found: {gr_id}")
        sc_id = lookup["sc_id"]
        if current_user["role"] != "admin" and lookup["sc_requester"] != current_user["user_id"]:
            raise PermissionDenied("Only the SC owner or admin can edit GRs")

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] == "denied":
                    raise ConflictError("Denied GR cannot be edited")
                if before["status"] not in ("draft", "manager_confirm", "pending", "approved"):
                    raise ConflictError("GR cannot be edited in its current status")

                updates = dict(data)
                if before["status"] in ("draft", "pending"):
                    allowed = {
                        key: updates[key]
                        for key in (
                            "po_id",
                            "requester_id",
                            "estimated_amount",
                            "tax_rate",
                            "remark",
                            "gr_no",
                            "pending_date",
                            "approved_date",
                            "goods_service_description",
                            "confirmation_name",
                            "delivery_from",
                            "delivery_to",
                            "last_delivery",
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
                    is_draft_gr = before["status"] == "draft"
                    if is_draft_gr:
                        # Draft GR: parent PO must be draft, SC must be draft
                        if po_sc["status"] != "draft":
                            raise ConflictError("Draft GR requires draft PO")
                        if po_sc["sc_status"] != "draft":
                            raise ConflictError("Draft GR requires draft SC")
                    else:
                        if po_sc["sc_status"] != "approved":
                            raise ConflictError("SC must be approved")
                        if po_sc["status"] != "active":
                            raise ConflictError("PO must be active")

                    # Recalculate gross_cost when estimated_amount or tax_rate changes
                    if "estimated_amount" in allowed or "tax_rate" in allowed:
                        merged["gross_cost"] = _compute_incl_tax(
                            Decimal(str(merged["estimated_amount"])),
                            merged.get("tax_rate"),
                        )

                    if not is_draft_gr:
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
                            gross_cost = ?,
                            tax_rate = ?,
                            remark = ?,
                            gr_no = ?,
                            pending_date = ?,
                            approved_date = ?,
                            goods_service_description = ?,
                            confirmation_name = ?,
                            delivery_from = ?,
                            delivery_to = ?,
                            last_delivery = ?
                        where gr_id = ?
                        """,
                        (
                            merged["po_id"],
                            merged["requester_id"],
                            float(amount),
                            float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
                            merged.get("tax_rate"),
                            merged.get("remark"),
                            merged.get("gr_no"),
                            merged.get("pending_date"),
                            merged.get("approved_date"),
                            merged.get("goods_service_description"),
                            merged.get("confirmation_name"),
                            merged.get("delivery_from"),
                            merged.get("delivery_to"),
                            merged.get("last_delivery"),
                            gr_id,
                        ),
                    )
                else:
                    allowed = {
                        key: updates[key]
                        for key in ("con_value", "tax_rate", "remark", "gr_no",
                                    "goods_service_description", "confirmation_name",
                                    "delivery_from", "delivery_to", "last_delivery")
                        if key in updates
                    }
                    if not allowed:
                        raise ValidationError("No GR fields to update")

                    merged = {**before, **allowed}
                    # Recalculate gross_cost when tax_rate changes on approved GR
                    if "tax_rate" in allowed:
                        merged["gross_cost"] = _compute_incl_tax(
                            Decimal(str(before["estimated_amount"] or 0)),
                            merged.get("tax_rate"),
                        )
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
                            gross_cost = ?,
                            tax_rate = ?,
                            remark = ?,
                            gr_no = ?,
                            goods_service_description = ?,
                            confirmation_name = ?,
                            delivery_from = ?,
                            delivery_to = ?,
                            last_delivery = ?
                        where gr_id = ?
                        """,
                        (float(con_value),
                         float(merged["gross_cost"]) if merged.get("gross_cost") is not None else None,
                         merged.get("tax_rate"), merged.get("remark"), merged.get("gr_no"),
                         merged.get("goods_service_description"), merged.get("confirmation_name"),
                         merged.get("delivery_from"), merged.get("delivery_to"), merged.get("last_delivery"),
                         gr_id),
                    )

                after = _get_gr(conn, gr_id)
                audit_sc_ids = [sc_id]
                if before["status"] == "pending" and after["po_id"] != before["po_id"]:
                    after_sc_id = _get_po_sc(conn, after["po_id"])["sc_id"]
                    if after_sc_id != sc_id:
                        audit_sc_ids.append(after_sc_id)
                for audit_sc_id in audit_sc_ids:
                    write_operation_record(
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


def deny_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    require_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] not in ("pending", "manager_confirm"):
                    raise ConflictError("GR must be pending or manager_confirm")

                timestamp = utc_now()
                conn.execute(
                    """
                    update gr_requests
                    set status = 'denied',
                        denied_by = ?,
                        denied_at = ?
                    where gr_id = ?
                    """,
                    (current_user["user_id"], timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_operation_record(
                    conn,
                    action_type="deny_gr",
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
                    conn, "gr", gr_id, "deny",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def finish_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    """Mark an approved GR as finished (goods received / service completed)."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)
                if before["status"] != "approved":
                    raise ConflictError("GR must be approved")

                timestamp = utc_now()
                conn.execute(
                    """
                    update gr_requests
                    set status = 'finished',
                        finished_by = ?,
                        finished_at = ?
                    where gr_id = ?
                    """,
                    (current_user["user_id"], timestamp, gr_id),
                )
                after = _get_gr(conn, gr_id)
                write_operation_record(
                    conn,
                    action_type="finish_gr",
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
                    conn, "gr", gr_id, "finish",
                    {"requester_id": sc["requester_id"]} if sc else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def recall_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    """Recall GR back to draft. Only the SC requester can recall, and only from manager_confirm or pending."""

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)
        sc = lookup_conn.execute(
            "SELECT requester_id, status FROM sc_records WHERE sc_id = ?",
            (sc_id,),
        ).fetchone()

    if sc is None:
        raise NotFound(f"SC {sc_id} not found")
    if sc["requester_id"] != current_user["user_id"]:
        raise PermissionDenied("Only the SC requester can recall GRs")

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _require_editable_parent_sc(conn, sc_id)
                before = _get_gr(conn, gr_id)

                if before["status"] not in ("manager_confirm", "pending"):
                    raise ConflictError("Only manager_confirm or pending GR can be recalled back to draft")

                timestamp = utc_now()
                conn.execute(
                    "update gr_requests set status = 'draft', confirmed_at = NULL, pending_date = NULL where gr_id = ?",
                    (gr_id,),
                )

                after = _get_gr(conn, gr_id)
                write_operation_record(
                    conn,
                    action_type="recall_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc_rec = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (sc_id,),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "gr", gr_id, "recall",
                    {"requester_id": sc_rec["requester_id"]} if sc_rec else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def delete_gr(config: AppConfig, current_user: dict, gr_id: str) -> dict:
    """Delete a draft GR and its attachments. Admin or GR owner."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_gr_sc_id(lookup_conn, gr_id)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_gr(conn, gr_id)
                if before["status"] != "draft":
                    raise ConflictError("Only draft GR can be deleted")
                if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the GR owner or admin can delete")

                # Collect attachment paths
                attach_rows = conn.execute(
                    "SELECT stored_path FROM attachments WHERE entity_type = 'gr' AND entity_id = ?",
                    (gr_id,),
                ).fetchall()
                attach_paths = [row["stored_path"] for row in attach_rows]

                # Delete attachments → GR
                conn.execute("DELETE FROM attachments WHERE entity_type = 'gr' AND entity_id = ?", (gr_id,))
                conn.execute("DELETE FROM gr_requests WHERE gr_id = ?", (gr_id,))

                write_operation_record(
                    conn,
                    action_type="delete_gr",
                    object_type="gr",
                    object_id=gr_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=None,
                )
                conn.commit()

                # Delete files from disk
                for path in attach_paths:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception:
                conn.rollback()
                raise

    return before
