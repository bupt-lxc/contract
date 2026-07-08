import json
from datetime import datetime, timezone
from decimal import Decimal
from math import isfinite
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.record_service import write_operation_record
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import (
    compute_po_budget,
    compute_po_fc_budget,
    compute_sc_budget,
    compute_sc_fc_budget,
)
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = (
    "requester_id",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
)
SUPPORTED_REQUEST_TYPES = {"FC", "call_off", "new"}
SUPPORTED_CURRENCIES = {"CNY", "EUR", "USD"}
SUPPORTED_STATUSES = {"manager_confirm", "pending", "approved", "denied", "finished"}
OPTIONAL_UPDATE_FIELDS = (
    "sc_no",
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
    "description",
    "asset",
    "asset_nums",
    "internal_system_number",
    "currency",
    "vendor_ids",
    "service_scope",
    "assignee_ids",
)
_VENDOR_SNAPSHOT_FIELDS = (
    "vendor_id",
    "vendor_name",
    "ksrm_vendor_code",
    "company_name_cn",
    "contact_person",
    "phone",
    "email",
    "service_scope",
    "description",
    "inquiry_history",
)
REQUIRED_BUSINESS_FIELDS = (
    "request_type",
    "cost_center",
    "sc_amount",
    "service_period_start",
    "service_period_end",
)


def _validate_calloff_po(conn, calloff_po_id: str | None, request_type: str | None, sc_amount, exclude_sc_id: str | None = None) -> None:
    """Validate call-off PO reference for call-off SC creation/submit."""
    if request_type == "call_off":
        if calloff_po_id is None:
            raise ValidationError("call_off request_type requires calloff_po_id")
    elif calloff_po_id is not None:
        raise ValidationError("calloff_po_id is only valid for call_off request_type")

    if calloff_po_id is None:
        if request_type == "FC":
            return
        return  # 'new' or 'call_off' without calloff_po_id handled above

    po_row = conn.execute(
        """select po.po_id, po.po_amount, po.status, sc.request_type as parent_sc_type,
                  po.request_type as po_request_type
           from pos po
           left join sc_records sc on sc.sc_id = po.sc_id
           where po.po_id = ?""",
        (calloff_po_id,),
    ).fetchone()
    if po_row is None:
        raise NotFound(f"PO not found: {calloff_po_id}")
    is_fc_po = (po_row["po_request_type"] == "FC" or po_row["parent_sc_type"] == "FC")
    if not is_fc_po:
        raise ValidationError("Call-off PO must belong to an FC-type SC or be an independent FC PO")
    if po_row["status"] != "active":
        raise ConflictError("Call-off PO must be active to create call-off SCs")

    if exclude_sc_id is not None:
        calloff_total = conn.execute(
            "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ? and sc_id != ?",
            (calloff_po_id, exclude_sc_id),
        ).fetchone()[0]
    else:
        calloff_total = conn.execute(
            "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ?",
            (calloff_po_id,),
        ).fetchone()[0]
    new_amount = Decimal(str(sc_amount)) if sc_amount is not None else Decimal("0")
    if Decimal(str(calloff_total)) + new_amount > Decimal(str(po_row["po_amount"])):
        raise ConflictError("Call-off SC total would exceed PO(FC) amount")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_sc_id(config: AppConfig, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"SC-{machine_id}-{today}-%"
    with connect(config) as conn:
        row = conn.execute(
            "SELECT sc_id FROM sc_records WHERE sc_id LIKE ? ORDER BY sc_id DESC LIMIT 1",
            (pattern,),
        ).fetchone()
    if row:
        last_seq = int(row["sc_id"].rsplit("-", 1)[-1])
        seq = last_seq + 1
    else:
        seq = 1
    return f"SC-{machine_id}-{today}-{seq:03d}"


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
    currency = data.get("currency", "CNY")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"currency must be one of: {', '.join(sorted(SUPPORTED_CURRENCIES))}")
    _positive_number(data["sc_amount"], "sc_amount")
    _validate_service_period(data)


def _assert_can_view_sc(user: dict, sc: dict, conn) -> None:
    if user.get("role") == "admin":
        return
    if sc["status"] == "draft":
        if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
            return
        raise PermissionDenied("SC is not visible")
    if user.get("role") == "requester" and user.get("user_id") == sc["requester_id"]:
        return
    # Allow assignees to view
    assignee_row = conn.execute(
        "SELECT 1 FROM sc_assignees WHERE sc_id = ? AND user_id = ?",
        (sc["sc_id"], user["user_id"]),
    ).fetchone()
    if assignee_row is not None:
        return
    raise PermissionDenied("SC is not visible")


def _assert_can_edit_sc(user: dict, sc: dict) -> None:
    if sc["status"] == "finished":
        raise ConflictError("Finished SC cannot be edited")
    if user.get("role") == "admin":
        return
    if sc["status"] in ("draft", "manager_confirm", "pending", "denied") and user.get("user_id") == sc["requester_id"]:
        return
    raise PermissionDenied("Admin permission required")


def _sc_permissions(user: dict, sc: dict) -> dict:
    is_admin = user.get("role") == "admin"
    is_owner = user.get("user_id") == sc["requester_id"]
    is_draft = sc["status"] == "draft"
    is_manager_confirm = sc["status"] == "manager_confirm"
    is_pending = sc["status"] == "pending"
    is_approved = sc["status"] == "approved"
    is_finished = sc["status"] == "finished"
    is_denied = sc["status"] == "denied"
    can_edit = (is_owner and (is_draft or is_pending or is_denied)) or (is_admin and not is_draft and not is_finished)
    can_manage = (is_admin or is_owner) and (is_draft or is_approved)
    return {
        "is_admin": is_admin,
        "can_edit_sc": can_edit,
        "can_submit_sc": (is_admin or is_owner) and (is_draft or is_denied),
        "can_confirm_sc": is_admin and is_manager_confirm,
        "can_approve_sc": is_admin and is_pending,
        "can_deny_sc": is_admin and (is_pending or is_manager_confirm),
        "can_finish_sc": (is_admin or is_owner) and is_approved,
        "can_recall_sc": is_owner and (is_pending or is_manager_confirm or is_approved or is_denied),
        "can_delete_sc": (is_admin or is_owner) and is_draft,
        "can_delete_po": is_admin or is_owner,
        "can_delete_gr": is_admin or is_owner,
        "can_finish_gr": is_admin or is_owner,
        "can_manage_po": can_manage,
        "can_manage_gr": can_manage,
        "can_transfer_sc": is_admin or is_owner,
    }


def _validate_service_period(data: dict) -> None:
    start = data.get("service_period_start")
    end = data.get("service_period_end")
    if start not in (None, "") and end not in (None, "") and start > end:
        raise ValidationError("service period is invalid")


def _sync_sc_assignees(conn, sc_id: str, assignee_ids: list[str] | None) -> None:
    """Replace the assignee associations for an SC with the given list."""
    if assignee_ids is None:
        return
    conn.execute("DELETE FROM sc_assignees WHERE sc_id = ?", (sc_id,))
    for uid in assignee_ids:
        conn.execute(
            "INSERT OR IGNORE INTO sc_assignees (sc_id, user_id) VALUES (?, ?)",
            (sc_id, uid),
        )


def _sync_sc_vendors(conn, sc_id: str, vendor_ids: list[str] | None) -> None:
    """Replace the vendor associations for an SC with the given list.

    Captures a JSON snapshot of each vendor's current state so historical
    SC records are unaffected by later vendor edits.
    """
    if vendor_ids is None:
        return
    conn.execute("DELETE FROM sc_vendors WHERE sc_id = ?", (sc_id,))
    for vid in vendor_ids:
        vendor_row = conn.execute(
            "SELECT * FROM vendors WHERE vendor_id = ?", (vid,)
        ).fetchone()
        snapshot = None
        if vendor_row is not None:
            snapshot_data = {
                field: vendor_row[field]
                for field in _VENDOR_SNAPSHOT_FIELDS
            }
            snapshot = json.dumps(snapshot_data, ensure_ascii=False)
        conn.execute(
            "INSERT OR IGNORE INTO sc_vendors (sc_id, vendor_id, vendor_snapshot) "
            "VALUES (?, ?, ?)",
            (sc_id, vid, snapshot),
        )


def _build_vendor_from_live(row) -> dict:
    """Extract vendor fields from a live JOIN row (backward compat fallback)."""
    return {
        "vendor_id": row["vendor_id"],
        "vendor_name": row["vendor_name"],
        "ksrm_vendor_code": row["ksrm_vendor_code"],
        "company_name_cn": row["company_name_cn"],
        "contact_person": row["contact_person"],
        "phone": row["phone"],
        "email": row["email"],
        "service_scope": row["service_scope"],
        "description": row["description"],
        "inquiry_history": row["inquiry_history"],
    }


def _fetch_sc_vendors(conn, sc_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT sv.vendor_snapshot,
               v.vendor_id, v.vendor_name, v.ksrm_vendor_code,
               v.company_name_cn, v.contact_person, v.phone, v.email,
               v.service_scope, v.description, v.inquiry_history
        FROM sc_vendors sv
        LEFT JOIN vendors v ON v.vendor_id = sv.vendor_id
        WHERE sv.sc_id = ?
        """,
        (sc_id,),
    ).fetchall()

    vendors = []
    for row in rows:
        if row["vendor_snapshot"] is not None:
            try:
                vendor = json.loads(row["vendor_snapshot"])
            except (json.JSONDecodeError, TypeError):
                vendor = _build_vendor_from_live(row)
        else:
            vendor = _build_vendor_from_live(row)
        vendors.append(vendor)

    vendors.sort(key=lambda v: v.get("vendor_name", ""))
    return vendors


def add_sc_vendor(config: AppConfig, current_user: dict, sc_id: str, vendor_id: str) -> list[dict]:
    """Associate a vendor with an SC (with snapshot). Returns updated vendor list."""
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                sc = _get_sc(conn, sc_id)
                if sc is None:
                    raise NotFound(f"SC {sc_id} not found")
                _assert_can_edit_sc(current_user, sc)

                # Verify vendor exists
                vendor_row = conn.execute(
                    "SELECT * FROM vendors WHERE vendor_id = ?", (vendor_id,)
                ).fetchone()
                if vendor_row is None:
                    raise NotFound(f"Vendor {vendor_id} not found")

                # Prevent duplicate
                existing = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sc_vendors WHERE sc_id = ? AND vendor_id = ?",
                    (sc_id, vendor_id),
                ).fetchone()
                if existing["cnt"] > 0:
                    raise ConflictError(f"Vendor {vendor_id} already associated with SC {sc_id}")

                # Build vendor snapshot
                snapshot_data = {}
                for field in _VENDOR_SNAPSHOT_FIELDS:
                    snapshot_data[field] = vendor_row[field]
                snapshot = json.dumps(snapshot_data, ensure_ascii=False)

                conn.execute(
                    "INSERT INTO sc_vendors (sc_id, vendor_id, vendor_snapshot) VALUES (?, ?, ?)",
                    (sc_id, vendor_id, snapshot),
                )

                updated_vendors = _fetch_sc_vendors(conn, sc_id)
                write_operation_record(
                    conn,
                    action_type="add_sc_vendor",
                    object_type="sc_vendor",
                    object_id=f"{sc_id}:{vendor_id}",
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after={"sc_id": sc_id, "vendor_id": vendor_id},
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return updated_vendors


def remove_sc_vendor(config: AppConfig, current_user: dict, sc_id: str, vendor_id: str) -> list[dict]:
    """Remove a vendor association from an SC. Returns updated vendor list."""
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                sc = _get_sc(conn, sc_id)
                if sc is None:
                    raise NotFound(f"SC {sc_id} not found")
                _assert_can_edit_sc(current_user, sc)

                cursor = conn.execute(
                    "DELETE FROM sc_vendors WHERE sc_id = ? AND vendor_id = ?",
                    (sc_id, vendor_id),
                )
                if cursor.rowcount == 0:
                    raise NotFound(f"Vendor {vendor_id} is not associated with SC {sc_id}")

                updated_vendors = _fetch_sc_vendors(conn, sc_id)
                write_operation_record(
                    conn,
                    action_type="remove_sc_vendor",
                    object_type="sc_vendor",
                    object_id=f"{sc_id}:{vendor_id}",
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before={"sc_id": sc_id, "vendor_id": vendor_id},
                    after=None,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return updated_vendors


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
              and gr.status in ('pending', 'manager_confirm', 'approved')
            """,
            (sc_id,),
        ).fetchall()

    allocated_po_amount = sum(po_amounts, Decimal("0"))
    if amount < allocated_po_amount:
        raise ConflictError("SC amount cannot be below allocated PO amount")

    gr_usage = sum(
        (
            Decimal(str(row["estimated_amount"] or 0))
            if row["status"] in ("pending", "manager_confirm")
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
    calloff_po_id = data.get("calloff_po_id")
    if data["request_type"] not in SUPPORTED_REQUEST_TYPES:
        raise ValidationError("request_type is invalid")
    currency = data.get("currency", "CNY")
    if currency not in SUPPORTED_CURRENCIES:
        raise ValidationError(f"currency must be one of: {', '.join(sorted(SUPPORTED_CURRENCIES))}")
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
    sc_id = _generate_sc_id(config, current_user["machine_id"])

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                _validate_calloff_po(conn, calloff_po_id, data["request_type"], sc_amount)
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
                      finished_at,
                      asset,
                      asset_nums,
                      pending_date,
                      approved_date,
                      internal_system_number,
                      calloff_po_id,
                      currency
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        timestamp if status == "finished" else None,
                        data.get("asset", "N"),
                        data.get("asset_nums"),
                        timestamp,
                        timestamp if status == "approved" else None,
                        data.get("internal_system_number"),
                        data.get("calloff_po_id"),
                        data.get("currency", "CNY"),
                    ),
                )
                created = _get_sc(conn, sc_id)
                write_operation_record(
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
    _require_fields(data, ("requester_id",))
    if (
        current_user["role"] == "requester"
        and data["requester_id"] != current_user["user_id"]
    ):
        raise PermissionDenied("Requester can only create their own draft SC")

    timestamp = utc_now()
    sc_id = _generate_sc_id(config, current_user["machine_id"])

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                calloff_po_id = data.get("calloff_po_id")
                _validate_calloff_po(conn, calloff_po_id, data.get("request_type"), data.get("sc_amount"))
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
                      finished_at,
                      asset,
                      asset_nums,
                      pending_date,
                      approved_date,
                      internal_system_number,
                      calloff_po_id,
                      currency
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        data.get("asset", "N"),
                        data.get("asset_nums"),
                        None,
                        None,
                        data.get("internal_system_number"),
                        data.get("calloff_po_id"),
                        data.get("currency", "CNY"),
                    ),
                )
                created = _get_sc(conn, sc_id)
                _sync_sc_vendors(conn, sc_id, data.get("vendor_ids"))
                _sync_sc_assignees(conn, sc_id, data.get("assignee_ids"))
                write_operation_record(
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
                if before["status"] not in ("draft", "denied"):
                    raise ConflictError("SC must be draft or denied to submit")

                # Admin can submit any draft; requester can only submit their own
                if (
                    current_user["role"] != "admin"
                    and (
                        current_user["role"] != "requester"
                        or before["requester_id"] != current_user["user_id"]
                    )
                ):
                    raise PermissionDenied("Only the draft owner or admin can submit this SC")
                merged = {**before, **data}
                _require_submit_fields(merged)

                calloff_po_id = before.get("calloff_po_id")
                _validate_calloff_po(conn, calloff_po_id, merged.get("request_type"), merged["sc_amount"], exclude_sc_id=sc_id)

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
                        asset = ?,
                        asset_nums = ?,
                        currency = ?,
                        status = 'manager_confirm',
                        submitted_date = ?,
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
                        merged.get("asset", "N"),
                        merged.get("asset_nums"),
                        merged.get("currency", "CNY"),
                        timestamp,
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                _sync_sc_vendors(conn, sc_id, merged.get("vendor_ids"))
                _sync_sc_assignees(conn, sc_id, merged.get("assignee_ids"))

                write_operation_record(
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


def confirm_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    """Admin confirms an SC in manager_confirm status, moving it to pending."""
    require_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "manager_confirm":
                    raise ConflictError("SC must be in manager_confirm status")

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set status = 'pending',
                        confirmed_at = ?,
                        pending_date = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (timestamp, timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_operation_record(
                    conn,
                    action_type="confirm_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "confirm", before, current_user
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
                if (
                    merged.get("currency") not in (None, "")
                    and merged["currency"] not in SUPPORTED_CURRENCIES
                ):
                    raise ValidationError(f"currency must be one of: {', '.join(sorted(SUPPORTED_CURRENCIES))}")
                if merged.get("sc_amount") not in (None, ""):
                    _positive_number(merged["sc_amount"], "sc_amount")
                _validate_service_period(merged)
                if "sc_amount" in allowed and merged.get("sc_amount") not in (None, ""):
                    _validate_sc_amount_not_below_usage(
                        config,
                        sc_id,
                        merged["sc_amount"],
                    )

                calloff_po_id = before.get("calloff_po_id")
                if calloff_po_id is not None and "sc_amount" in allowed:
                    po_row = conn.execute(
                        "select po_amount from pos where po_id = ?",
                        (calloff_po_id,),
                    ).fetchone()
                    if po_row:
                        sibling_total = conn.execute(
                            "select coalesce(sum(sc_amount), 0) from sc_records "
                            "where calloff_po_id = ? and sc_id != ?",
                            (calloff_po_id, sc_id),
                        ).fetchone()[0]
                        if Decimal(str(sibling_total)) + Decimal(str(merged["sc_amount"])) > Decimal(str(po_row["po_amount"])):
                            raise ConflictError("Call-off SC total would exceed PO(FC) amount")

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
                        asset = ?,
                        asset_nums = ?,
                        internal_system_number = ?,
                        currency = ?,
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
                        merged.get("asset"),
                        merged.get("asset_nums"),
                        merged.get("internal_system_number"),
                        merged.get("currency"),
                        timestamp,
                        sc_id,
                    ),
                )
                after = _get_sc(conn, sc_id)
                if "vendor_ids" in allowed:
                    _sync_sc_vendors(conn, sc_id, allowed["vendor_ids"])
                if "assignee_ids" in allowed:
                    _sync_sc_assignees(conn, sc_id, allowed["assignee_ids"])
                write_operation_record(
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
                if before["status"] not in ("pending", "manager_confirm"):
                    raise ConflictError("SC must be pending or manager_confirm")

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
                write_operation_record(
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


def finish_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "approved":
                    raise ConflictError("SC must be approved")

                # Block if any PO is not finished
                unfinished_pos = conn.execute(
                    "SELECT po_id, status FROM pos WHERE sc_id = ? AND status != 'finished'",
                    (sc_id,),
                ).fetchall()
                if unfinished_pos:
                    raise ConflictError(
                        f"Cannot finish SC: {len(unfinished_pos)} PO(s) not finished. "
                        "Finish all POs first."
                    )

                # Block if any GR is not in a final state
                non_final_grs = conn.execute(
                    """
                    SELECT gr.gr_id, gr.status
                    FROM gr_requests gr
                    JOIN pos po ON po.po_id = gr.po_id
                    WHERE po.sc_id = ? AND gr.status NOT IN ('approved', 'denied', 'finished')
                    """,
                    (sc_id,),
                ).fetchall()
                if non_final_grs:
                    raise ConflictError(
                        f"Cannot finish SC: {len(non_final_grs)} GR(s) not in final state. "
                        "Approve, deny or finish all GRs first."
                    )

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set status = 'finished',
                        finished_at = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_operation_record(
                    conn,
                    action_type="finish_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "finish", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def transfer_sc(config: AppConfig, current_user: dict, sc_id: str, new_requester_id: str) -> dict:
    """Transfer SC ownership to another user. Admin or current owner can transfer."""
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                before = _get_sc(conn, sc_id)

                perms = _sc_permissions(current_user, before)
                if not perms["can_transfer_sc"]:
                    raise PermissionDenied("没有权限转移此 SC 的所有者")

                target = conn.execute(
                    "SELECT user_id FROM users WHERE user_id = ?",
                    (new_requester_id,),
                ).fetchone()
                if target is None:
                    raise ValidationError(f"目标用户不存在: {new_requester_id}")

                if before["requester_id"] == new_requester_id:
                    return before

                timestamp = utc_now()
                conn.execute(
                    "UPDATE sc_records SET requester_id = ?, updated_at = ? WHERE sc_id = ?",
                    (new_requester_id, timestamp, sc_id),
                )

                after = _get_sc(conn, sc_id)

                write_operation_record(
                    conn,
                    action_type="transfer_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )

                conn.commit()
                return after
            except Exception:
                conn.rollback()
                raise


def recall_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    """Recall SC back to draft. Only the requester can recall.
    Requires that the SC has no non-draft POs."""
    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before is None:
                    raise NotFound(f"SC {sc_id} not found")

                if before["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the SC requester can recall")
                if before["status"] not in ("manager_confirm", "pending", "approved", "denied"):
                    raise ConflictError("SC cannot be recalled back to draft in its current status")

                non_draft_po_count = conn.execute(
                    "select count(*) from pos where sc_id = ? and status != 'draft'",
                    (sc_id,),
                ).fetchone()[0]
                if non_draft_po_count > 0:
                    raise ConflictError("Cannot recall SC with existing non-draft POs")

                timestamp = utc_now()
                conn.execute(
                    "update sc_records set status = 'draft', confirmed_at = NULL, pending_date = NULL, updated_at = ? where sc_id = ?",
                    (timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_operation_record(
                    conn,
                    action_type="recall_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                notification_service.queue_status_change(
                    conn, "sc", sc_id, "recall", before, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def delete_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    """Delete a draft SC and its attachments. Admin or SC owner."""
    require_requester_or_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "draft":
                    raise ConflictError("Only draft SC can be deleted")
                if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the SC owner or admin can delete")

                # Collect attachment file paths before deleting DB records
                attach_rows = conn.execute(
                    "SELECT stored_path FROM attachments WHERE entity_type = 'sc' AND entity_id = ?",
                    (sc_id,),
                ).fetchall()
                attach_paths = [row["stored_path"] for row in attach_rows]

                # Also collect PO/GR attachments under this SC
                po_ids = [row["po_id"] for row in conn.execute(
                    "SELECT po_id FROM pos WHERE sc_id = ?", (sc_id,),
                )]
                for po_id in po_ids:
                    gr_rows = conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'gr' AND entity_id IN ("
                        "SELECT gr_id FROM gr_requests WHERE po_id = ?)",
                        (po_id,),
                    ).fetchall()
                    attach_paths.extend(row["stored_path"] for row in gr_rows)
                    po_attach = conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'po' AND entity_id = ?",
                        (po_id,),
                    ).fetchall()
                    attach_paths.extend(row["stored_path"] for row in po_attach)

                # Delete attachment DB records for this SC and its POs/GRs
                conn.execute(
                    "DELETE FROM attachments WHERE entity_type = 'sc' AND entity_id = ?",
                    (sc_id,),
                )
                for po_id in po_ids:
                    conn.execute(
                        "DELETE FROM attachments WHERE entity_type = 'po' AND entity_id = ?",
                        (po_id,),
                    )
                    conn.execute(
                        "DELETE FROM attachments WHERE entity_type = 'gr' AND entity_id IN ("
                        "SELECT gr_id FROM gr_requests WHERE po_id = ?)",
                        (po_id,),
                    )
                # Delete GRs → POs → SC (and junction table)
                for po_id in po_ids:
                    conn.execute("DELETE FROM gr_requests WHERE po_id = ?", (po_id,))
                    conn.execute("DELETE FROM pos WHERE po_id = ?", (po_id,))
                conn.execute("DELETE FROM sc_vendors WHERE sc_id = ?", (sc_id,))
                conn.execute("DELETE FROM sc_assignees WHERE sc_id = ?", (sc_id,))
                conn.execute("DELETE FROM sc_records WHERE sc_id = ?", (sc_id,))

                write_operation_record(
                    conn,
                    action_type="delete_sc",
                    object_type="sc",
                    object_id=sc_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=None,
                )
                conn.commit()

                # Delete files from disk after successful commit
                for path in attach_paths:
                    try:
                        Path(path).unlink(missing_ok=True)
                    except OSError:
                        pass
            except Exception:
                conn.rollback()
                raise

    return {"deleted": True, "sc_id": sc_id}


def get_sc_detail(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    with connect(config) as conn:
        sc = _get_sc(conn, sc_id)
        _assert_can_view_sc(current_user, sc, conn)
        pos = [
            _row_to_dict(row)
            for row in conn.execute(
                """select po.*, v.vendor_name, v.ksrm_vendor_code
                   from pos po
                   join vendors v on v.vendor_id = po.vendor_id
                   where po.sc_id = ?
                   order by po.created_at, po.po_id""",
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
        records = [
            _row_to_dict(row)
            for row in conn.execute(
                """
                select *
                from operation_records
                where sc_id = ?
                order by created_at desc
                """,
                (sc_id,),
            )
        ]

        # For call-off SCs, include parent PO(FC) info
        parent_po = None
        if sc.get("calloff_po_id"):
            parent_po_row = conn.execute(
                """select po.*, sc_parent.request_type as parent_sc_type
                   from pos po
                   left join sc_records sc_parent on sc_parent.sc_id = po.sc_id
                   where po.po_id = ?""",
                (sc["calloff_po_id"],),
            ).fetchone()
            if parent_po_row:
                parent_po = _row_to_dict(parent_po_row)

        vendors = _fetch_sc_vendors(conn, sc_id)
        assignee_rows = conn.execute(
            """SELECT u.user_id, u.user_name
               FROM sc_assignees sa
               JOIN users u ON u.user_id = sa.user_id
               WHERE sa.sc_id = ?
               ORDER BY u.user_name""",
            (sc_id,),
        ).fetchall()
        assignees = [_row_to_dict(r) for r in assignee_rows]

    if parent_po is not None:
        parent_po["fc_budget"] = compute_po_fc_budget(config, sc["calloff_po_id"])

    for po in pos:
        if sc["request_type"] == "FC":
            po_budget = compute_po_fc_budget(config, po["po_id"])
            po["open_po_amount"] = po_budget["open_po_amount"]
            po["allocated_calloff_amount"] = po_budget["allocated_calloff_amount"]
            po["pending_calloff_amount"] = po_budget["pending_calloff_amount"]
            po["downstream_consumed"] = po_budget["downstream_consumed"]
            po["downstream_pending_gr"] = po_budget["downstream_pending_gr"]
            po["downstream_pending_gr_tax"] = po_budget["downstream_pending_gr_tax"]
        else:
            po["budget"] = compute_po_budget(config, po["po_id"])
            po["open_po_amount"] = po["budget"]["open_po_amount"]
            po["consumed_amount"] = po["budget"]["po_con_value_total"]
            po["pending_total"] = po["budget"]["po_pending_total"]
            po["pending_total_incl_tax"] = po["budget"]["po_pending_total_incl_tax"]

    for po in pos:
        po["sc_request_type"] = sc["request_type"]

    if sc["request_type"] == "FC":
        sc_budget = compute_sc_fc_budget(config, sc_id)
    else:
        sc_budget = compute_sc_budget(config, sc_id)

    return {
        "sc": sc,
        "budget": sc_budget,
        "pos": pos,
        "grs": grs,
        "operation_records": records,
        "permissions": _sc_permissions(current_user, sc),
        "vendors": vendors,
        "assignees": assignees,
        "parent_po": parent_po,
    }


def approve_sc(config: AppConfig, current_user: dict, sc_id: str) -> dict:
    """Approve an SC (pending → approved). Admin only."""
    require_admin(current_user)

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_sc(conn, sc_id)
                if before["status"] != "pending":
                    raise ConflictError("SC must be pending")
                if not before.get("sc_no"):
                    raise ConflictError("Cannot approve SC without SC No")

                timestamp = utc_now()
                conn.execute(
                    """
                    update sc_records
                    set status = 'approved',
                        approved_by = ?,
                        approved_at = ?,
                        approved_date = ?,
                        updated_at = ?
                    where sc_id = ?
                    """,
                    (current_user["user_id"], timestamp, timestamp, timestamp, sc_id),
                )
                after = _get_sc(conn, sc_id)
                write_operation_record(
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
