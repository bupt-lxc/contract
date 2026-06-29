from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, PermissionDenied, ValidationError
from sc_gr_app.rbac import require_admin, require_requester_or_admin
from sc_gr_app.services.record_service import write_operation_record
from sc_gr_app.services import notification_service
from sc_gr_app.services.budget_service import compute_sc_budget_decimal
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("sc_id", "vendor_id", "po_amount")
SUPPORTED_STATUSES = {"draft", "activing", "finished"}


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
          and status in ('pending', 'manager_confirm', 'approved')
        """,
        (po_id,),
    )
    for row in rows:
        if row["status"] in ("pending", "manager_confirm"):
            usage += Decimal(str(row["estimated_amount"]))
        else:
            usage += Decimal(str(row["con_value"]))
    return usage


def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    po_amount = _positive_number(data["po_amount"], "po_amount")

    sc_id = data["sc_id"]
    timestamp = utc_now()

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        po_id = _generate_po_id(config, current_user["machine_id"])
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                sc = conn.execute(
                    "select * from sc_records where sc_id = ?",
                    (sc_id,),
                ).fetchone()
                if sc is None:
                    raise NotFound(f"SC not found: {sc_id}")

                sc_status = sc["status"]
                if sc_status not in ("draft", "approved"):
                    raise ConflictError("SC must be draft or approved")

                # Derive PO status from SC context
                status = data.get("status")
                if status is None:
                    status = "draft" if sc_status == "draft" else "activing"
                elif status not in SUPPORTED_STATUSES:
                    raise ValidationError("status is invalid")
                # Enforce: draft SC → draft PO only
                if sc_status == "draft" and status != "draft":
                    raise ConflictError("Draft SC only allows draft PO")
                if sc_status == "approved" and status == "draft":
                    raise ConflictError("Approved SC does not allow draft PO")

                if current_user["role"] != "admin" and sc["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the SC owner or admin can create POs")

                vendor = conn.execute(
                    "select vendor_id from vendors where vendor_id = ?",
                    (data["vendor_id"],),
                ).fetchone()
                if vendor is None:
                    raise NotFound(f"Vendor not found: {data['vendor_id']}")

                sc_vendor = conn.execute(
                    "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                    (sc_id, data["vendor_id"]),
                ).fetchone()
                if sc_vendor is None:
                    raise ValidationError(
                        f"Vendor {data['vendor_id']} is not linked to SC {sc_id}"
                    )

                is_draft = status == "draft"
                if not is_draft:
                    budget = compute_sc_budget_decimal(config, sc_id)
                    if budget["allocated_po_amount"] + po_amount > Decimal(
                        str(sc["sc_amount"])
                    ):
                        raise ConflictError("PO total would exceed SC amount")

                activing_date_value = None if is_draft else timestamp

                conn.execute(
                    """
                    insert into pos (
                      po_id,
                      sc_id,
                      vendor_id,
                      po_no,
                      requester_id,
                      po_amount,
                      status,
                      contract_from,
                      contract_to,
                      contract_no,
                      payment_frequency,
                      contract_pos,
                      contract_type,
                      cost_center,
                      purchaser,
                      activing_date,
                      created_at,
                      updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        po_id,
                        sc_id,
                        data["vendor_id"],
                        data.get("po_no"),
                        sc["requester_id"],
                        float(po_amount),
                        status,
                        data.get("contract_from"),
                        data.get("contract_to"),
                        data.get("contract_no"),
                        data.get("payment_frequency"),
                        data.get("contract_pos"),
                        data.get("contract_type"),
                        data.get("cost_center") or str(sc["cost_center"]) if sc["cost_center"] is not None else None,
                        data.get("purchaser"),
                        activing_date_value,
                        timestamp,
                        timestamp,
                    ),
                )
                created = _get_po(conn, po_id)
                write_operation_record(
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
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created


def _submit_po_drafts(conn, po_ids: list[str], timestamp: str) -> list[dict]:
    """Submit draft POs in-place on an existing connection (no lock acquisition).

    Used internally by approve_sc for cascade submission.
    Returns list of submitted PO dicts.
    """
    submitted = []
    for po_id in po_ids:
        before = _get_po_or_raise(conn, po_id)
        if before["status"] != "draft":
            raise ConflictError(f"PO must be draft to submit: {po_id}")

        conn.execute(
            """
            update pos
            set status = 'activing',
                activing_date = ?,
                updated_at = ?
            where po_id = ?
            """,
            (timestamp, timestamp, po_id),
        )
        after = _get_po_or_raise(conn, po_id)
        write_operation_record(
            conn,
            action_type="submit_po",
            object_type="po",
            object_id=po_id,
            sc_id=after["sc_id"],
            operator_id=after.get("created_by", "SYSTEM"),
            machine_id="SYSTEM_CASCADE",
            before=before,
            after=after,
        )
        sc = conn.execute(
            "SELECT requester_id FROM sc_records WHERE sc_id = ?",
            (after["sc_id"],),
        ).fetchone()
        notification_service.queue_status_change(
            conn, "po", po_id, "submit",
            {"requester_id": sc["requester_id"]} if sc else {},
            {"user_id": after.get("created_by", "SYSTEM"), "machine_id": "SYSTEM_CASCADE"}
        )
        submitted.append(after)
    return submitted


def submit_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Manually submit a draft PO to activing status (with budget check)."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        sc_id = _get_po_or_raise(lookup_conn, po_id)["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("PO must be draft to submit")

                # SC must not be draft for PO submission
                sc = conn.execute(
                    "SELECT status, sc_amount FROM sc_records WHERE sc_id = ?", (sc_id,)
                ).fetchone()
                if sc is None:
                    raise ConflictError("SC not found")
                if sc["status"] == "draft":
                    raise ConflictError("Cannot submit PO while SC is still draft. Submit the SC first.")

                # Budget check at submission time (skip if SC has no amount set)
                if sc["sc_amount"] is not None:
                    po_amount = Decimal(str(before["po_amount"]))
                    budget = compute_sc_budget_decimal(config, sc_id)
                    if budget["allocated_po_amount"] + po_amount > Decimal(
                        str(sc["sc_amount"])
                    ):
                        raise ConflictError("PO total would exceed SC amount")

                timestamp = utc_now()
                _submit_po_drafts(conn, [po_id], timestamp)
                after = _get_po_or_raise(conn, po_id)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def update_po(config: AppConfig, current_user: dict, po_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    allowed_fields = {
        "vendor_id",
        "po_no",
        "po_amount",
        "contract_from",
        "contract_to",
        "contract_no",
        "payment_frequency",
        "contract_pos",
        "contract_type",
        "cost_center",
        "purchaser",
        "activing_date",
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
                if sc["status"] == "finished":
                    raise ConflictError("Finished SC cannot be edited")
                if before["status"] == "finished":
                    raise ConflictError("Finished PO cannot be edited")
                if before["status"] == "draft" and sc["status"] == "finished":
                    raise ConflictError("Finished SC cannot be edited")
                if current_user["role"] != "admin" and sc["requester_id"] != current_user["user_id"]:
                    raise PermissionDenied("Only the SC owner or admin can edit POs")

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
                    sc_vendor = conn.execute(
                        "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                        (sc_id, merged["vendor_id"]),
                    ).fetchone()
                    if sc_vendor is None:
                        raise ValidationError(
                            f"Vendor {merged['vendor_id']} is not linked to SC {sc_id}"
                        )

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
                        contract_pos = ?,
                        contract_type = ?,
                        cost_center = ?,
                        purchaser = ?,
                        activing_date = ?,
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
                        merged.get("contract_pos"),
                        merged.get("contract_type"),
                        merged.get("cost_center"),
                        merged.get("purchaser"),
                        merged.get("activing_date"),
                        timestamp,
                        po_id,
                    ),
                )
                after = _get_po_or_raise(conn, po_id)
                write_operation_record(
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



def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_requester_or_admin(current_user)

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
                if sc["status"] == "finished":
                    raise ConflictError("Finished SC cannot be edited")
                if before["status"] != "activing":
                    raise ConflictError("PO must be activing")

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
                write_operation_record(
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


def recall_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Recall PO back to draft. Only the SC requester can recall, and only from activing.
    Requires that the PO has no non-draft GRs."""

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]
        sc = lookup_conn.execute(
            "select status, requester_id from sc_records where sc_id = ?",
            (sc_id,),
        ).fetchone()

    if sc is None:
        raise NotFound(f"SC {sc_id} not found")
    if sc["requester_id"] != current_user["user_id"]:
        raise PermissionDenied("Only the SC requester can recall POs")
    if sc["status"] == "finished":
        raise ConflictError("Finished SC cannot be edited")

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

                if before["status"] != "activing":
                    raise ConflictError("Only activing PO can be recalled back to draft")

                non_draft_gr_count = conn.execute(
                    "select count(*) from gr_requests where po_id = ? and status != 'draft'",
                    (po_id,),
                ).fetchone()[0]
                if non_draft_gr_count > 0:
                    raise ConflictError("Cannot recall PO with existing non-draft GRs")

                timestamp = utc_now()
                conn.execute(
                    "update pos set status = 'draft', updated_at = ? where po_id = ?",
                    (timestamp, po_id),
                )
                after = _get_po_or_raise(conn, po_id)
                write_operation_record(
                    conn,
                    action_type="recall_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=sc_id,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                sc_requester = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                notification_service.queue_status_change(
                    conn, "po", po_id, "recall",
                    {"requester_id": sc_requester["requester_id"]} if sc_requester else {}, current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def delete_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Delete a draft PO and its GRs/attachments. Admin or SC owner."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

    with LeaseLock(config.lock_dir, f"sc:{sc_id}", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("Only draft PO can be deleted")
                sc = conn.execute(
                    "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                    (before["sc_id"],),
                ).fetchone()
                if current_user["role"] != "admin" and (
                    sc is None or sc["requester_id"] != current_user["user_id"]
                ):
                    raise PermissionDenied("Only the SC owner or admin can delete")

                # Collect attachment paths
                attach_paths = [
                    row["stored_path"] for row in conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'po' AND entity_id = ?",
                        (po_id,),
                    ).fetchall()
                ]
                attach_paths.extend(
                    row["stored_path"] for row in conn.execute(
                        "SELECT stored_path FROM attachments WHERE entity_type = 'gr' AND entity_id IN ("
                        "SELECT gr_id FROM gr_requests WHERE po_id = ?)",
                        (po_id,),
                    ).fetchall()
                )

                # Delete GRs → PO → attachments
                conn.execute("DELETE FROM attachments WHERE entity_type = 'gr' AND entity_id IN ("
                             "SELECT gr_id FROM gr_requests WHERE po_id = ?)", (po_id,))
                conn.execute("DELETE FROM gr_requests WHERE po_id = ?", (po_id,))
                conn.execute("DELETE FROM attachments WHERE entity_type = 'po' AND entity_id = ?", (po_id,))
                conn.execute("DELETE FROM pos WHERE po_id = ?", (po_id,))

                write_operation_record(
                    conn,
                    action_type="delete_po",
                    object_type="po",
                    object_id=po_id,
                    sc_id=before["sc_id"],
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
