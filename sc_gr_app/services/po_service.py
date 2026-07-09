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
    compute_po_budget,
    compute_po_fc_budget,
    compute_sc_budget_decimal,
)
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("vendor_id", "po_amount")
SUPPORTED_STATUSES = {"draft", "active", "finished"}


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
          and status IN ('approved', 'finished')
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


def _assert_can_view_po(current_user: dict, po: dict, conn) -> None:
    if current_user.get("role") == "admin":
        return
    if (
        current_user.get("role") == "requester"
        and current_user.get("user_id") == po["requester_id"]
    ):
        return
    if po.get("sc_id"):
        assignee_row = conn.execute(
            "SELECT 1 FROM sc_assignees WHERE sc_id = ? AND user_id = ?",
            (po["sc_id"], current_user.get("user_id")),
        ).fetchone()
        if assignee_row is not None:
            return
    raise PermissionDenied("PO is not visible")


def _po_permissions(current_user: dict, po: dict) -> dict:
    is_admin = current_user.get("role") == "admin"
    is_owner = current_user.get("user_id") == po["requester_id"]
    can_manage = (is_admin or is_owner) and po["status"] in ("draft", "active")
    return {
        "is_admin": is_admin,
        "can_delete_po": is_admin or is_owner,
        "can_manage_po": can_manage,
        "can_manage_gr": can_manage,
    }


def get_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    return get_po_detail(config, current_user, po_id)["po"]


def get_po_detail(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Return PO detail for independent PO routes.

    SC-linked detail pages still load through get_sc_detail, but this endpoint
    also supports linked POs for deep links and protocol navigation.
    """
    with connect(config) as conn:
        row = conn.execute(
            """
            select
              po.*,
              sc.sc_no,
              coalesce(po.request_type, sc.request_type) as sc_request_type,
              u.user_name as requester_name,
              vendor.vendor_name,
              vendor.ksrm_vendor_code
            from pos po
            left join sc_records sc on sc.sc_id = po.sc_id
            join users u on u.user_id = po.requester_id
            join vendors vendor on vendor.vendor_id = po.vendor_id
            where po.po_id = ?
            """,
            (po_id,),
        ).fetchone()
        if row is None:
            raise NotFound(f"PO not found: {po_id}")

        po = _row_to_dict(row)
        _assert_can_view_po(current_user, po, conn)

        records = [
            _row_to_dict(record)
            for record in conn.execute(
                """
                select *
                from operation_records
                where object_type = 'po' and object_id = ?
                order by created_at desc
                """,
                (po_id,),
            )
        ]

        calloff_scs = [
            _row_to_dict(sc)
            for sc in conn.execute(
                """
                select sc.*, u.user_name as requester_name
                from sc_records sc
                left join users u on u.user_id = sc.requester_id
                where sc.calloff_po_id = ?
                order by sc.created_at, sc.sc_id
                """,
                (po_id,),
            )
        ]

    is_fc_po = po.get("sc_request_type") == "FC"
    if is_fc_po:
        po_budget = compute_po_fc_budget(config, po_id)
        po["open_po_amount"] = po_budget["open_po_amount"]
        po["allocated_calloff_amount"] = po_budget["allocated_calloff_amount"]
        po["pending_calloff_amount"] = po_budget["pending_calloff_amount"]
        po["downstream_consumed"] = po_budget["downstream_consumed"]
        po["downstream_pending_gr"] = po_budget["downstream_pending_gr"]
        po["downstream_pending_gr_tax"] = po_budget["downstream_pending_gr_tax"]
    else:
        po["budget"] = compute_po_budget(config, po_id)
        po["open_po_amount"] = po["budget"]["open_po_amount"]
        po["consumed_amount"] = po["budget"]["po_con_value_total"]
        po["pending_total"] = po["budget"]["po_pending_total"]
        po["pending_total_incl_tax"] = po["budget"]["po_pending_total_incl_tax"]

    return {
        "po": po,
        "calloff_scs": calloff_scs if is_fc_po else [],
        "operation_records": records,
        "permissions": _po_permissions(current_user, po),
    }


def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    po_amount = _positive_number(data["po_amount"], "po_amount")

    sc_id = data.get("sc_id")
    request_type = data.get("request_type")
    timestamp = utc_now()

    # Semantic validation
    if sc_id and request_type == "FC":
        raise ValidationError(
            "request_type 'FC' is not valid when sc_id is provided; "
            "use independent FC PO without sc_id"
        )
    if not sc_id and request_type != "FC":
        raise ValidationError(
            "request_type must be 'FC' when creating an independent PO without sc_id"
        )

    machine_id = current_user["machine_id"]

    if sc_id:
        # SC-linked PO branch
        with LeaseLock(config.lock_dir, f"sc:{sc_id}", machine_id):
            po_id = _generate_po_id(config, machine_id)
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
                        status = "draft" if sc_status == "draft" else "active"
                    elif status not in SUPPORTED_STATUSES:
                        raise ValidationError("status is invalid")
                    # Enforce: draft SC → draft PO only
                    if sc_status == "draft" and status != "draft":
                        raise ConflictError("Draft SC only allows draft PO")

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

                    active_date_value = None if is_draft else timestamp

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
                          active_date,
                          created_at,
                          updated_at,
                          request_type
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            active_date_value,
                            timestamp,
                            timestamp,
                            None,  # request_type NULL for SC-linked POs
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
                        machine_id=machine_id,
                        before=None,
                        after=created,
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise
    else:
        # Independent FC PO branch
        # Serialize ID generation per machine to prevent duplicate IDs
        with LeaseLock(config.lock_dir, f"po:gen:{machine_id}", machine_id):
            po_id = _generate_po_id(config, machine_id)
        with LeaseLock(config.lock_dir, f"po:{po_id}", machine_id):
            with connect(config) as conn:
                try:
                    conn.execute("BEGIN IMMEDIATE")

                    # Vendor existence check
                    vendor = conn.execute(
                        "select vendor_id from vendors where vendor_id = ?",
                        (data["vendor_id"],),
                    ).fetchone()
                    if vendor is None:
                        raise NotFound(f"Vendor not found: {data['vendor_id']}")

                    status = data.get("status", "draft")
                    if status not in SUPPORTED_STATUSES:
                        raise ValidationError("status is invalid")

                    is_draft = status == "draft"
                    active_date_value = None if is_draft else timestamp

                    requester_id = (
                        data.get("requester_id")
                        if current_user.get("role") == "admin" and data.get("requester_id")
                        else current_user["user_id"]
                    )

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
                          active_date,
                          created_at,
                          updated_at,
                          request_type
                        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            po_id,
                            None,  # sc_id NULL for independent FC PO
                            data["vendor_id"],
                            data.get("po_no"),
                            requester_id,
                            float(po_amount),
                            status,
                            data.get("contract_from"),
                            data.get("contract_to"),
                            data.get("contract_no"),
                            data.get("payment_frequency"),
                            data.get("contract_pos"),
                            data.get("contract_type"),
                            data.get("cost_center"),
                            data.get("purchaser"),
                            active_date_value,
                            timestamp,
                            timestamp,
                            "FC",
                        ),
                    )
                    created = _get_po(conn, po_id)
                    write_operation_record(
                        conn,
                        action_type="create_po",
                        object_type="po",
                        object_id=po_id,
                        sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=created,
                    )
                    notification_service.queue_status_change(
                        conn, "po", po_id, "create",
                        {"requester_id": requester_id}, current_user
                    )
                    conn.commit()
                except Exception:
                    conn.rollback()
                    raise

    return created


def _submit_po_drafts(conn, po_ids: list[str], timestamp: str) -> list[dict]:
    """Submit draft POs in-place on an existing connection (no lock acquisition).

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
            set status = 'active',
                active_date = ?,
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
        if after.get("sc_id"):
            sc = conn.execute(
                "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                (after["sc_id"],),
            ).fetchone()
        else:
            sc = None
        notification_service.queue_status_change(
            conn, "po", po_id, "submit",
            {"requester_id": sc["requester_id"]} if sc else {"requester_id": after.get("requester_id")},
            {"user_id": after.get("created_by", "SYSTEM"), "machine_id": "SYSTEM_CASCADE"}
        )
        submitted.append(after)
    return submitted


def submit_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Manually submit a draft PO to active status (with budget check)."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"
    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("PO must be draft to submit")

                timestamp = utc_now()

                if sc_id:
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
        "active_date",
    }
    updates = {key: value for key, value in data.items() if key in allowed_fields}
    if not updates:
        raise ValidationError("No PO fields to update")

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"
    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

                sc = None
                if sc_id:
                    sc = conn.execute(
                        "select * from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    if sc is None:
                        raise NotFound(f"SC not found: {sc_id}")
                    if sc["status"] == "finished":
                        raise ConflictError("Finished SC cannot be edited")
                    if before["status"] == "draft" and sc["status"] == "finished":
                        raise ConflictError("Finished SC cannot be edited")
                    if current_user["role"] != "admin" and sc["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the SC owner or admin can edit POs")
                else:
                    if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the PO owner or admin can edit POs")

                if before["status"] == "finished":
                    raise ConflictError("Finished PO cannot be edited")

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
                    if sc_id:
                        sc_vendor = conn.execute(
                            "select 1 from sc_vendors where sc_id = ? and vendor_id = ?",
                            (sc_id, merged["vendor_id"]),
                        ).fetchone()
                        if sc_vendor is None:
                            raise ValidationError(
                                f"Vendor {merged['vendor_id']} is not linked to SC {sc_id}"
                            )

                if sc_id:
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

                # FC PO call-off amount check (effective FC type)
                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id and sc:
                    is_fc = sc["request_type"] == "FC"

                if is_fc and "po_amount" in updates:
                    calloff_total = conn.execute(
                        "select coalesce(sum(sc_amount), 0) from sc_records where calloff_po_id = ?",
                        (po_id,),
                    ).fetchone()[0]
                    if po_amount < Decimal(str(calloff_total)):
                        raise ConflictError("PO amount cannot be below allocated call-off SC amounts")

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
                        active_date = ?,
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
                        merged.get("active_date"),
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



def _finish_po_in_transaction(conn, po_id: str, current_user: dict, timestamp: str) -> dict:
    """Finish a PO within an existing transaction. Must NOT acquire locks."""
    before = _get_po_or_raise(conn, po_id)

    sc = None
    if before.get("sc_id"):
        sc = conn.execute(
            "select status, requester_id from sc_records where sc_id = ?",
            (before["sc_id"],),
        ).fetchone()
        if sc and sc["status"] == "finished":
            raise ConflictError("Finished SC cannot be edited")

    if before["status"] != "active":
        raise ConflictError("PO must be active")

    conn.execute(
        """
        update pos
        set status = 'finished',
            updated_at = ?,
            finished_at = ?,
            finished_by = ?
        where po_id = ?
        """,
        (timestamp, timestamp, current_user["user_id"], po_id),
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
    notification_service.queue_status_change(
        conn, "po", po_id, "finish",
        {"requester_id": sc["requester_id"]} if sc else {"requester_id": before["requester_id"]}, current_user
    )
    return after


def finish_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"
    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

                # Effective FC type check
                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc:
                    non_final_calloffs = conn.execute(
                        """
                        SELECT sc_id, status FROM sc_records
                        WHERE calloff_po_id = ? AND status NOT IN ('finished', 'denied')
                        """,
                        (po_id,),
                    ).fetchall()
                    if non_final_calloffs:
                        raise ConflictError(
                            f"Cannot finish PO: {len(non_final_calloffs)} call-off SC(s) not in final state. "
                            "Finish or deny all call-off SCs first."
                        )
                else:
                    non_final_grs = conn.execute(
                        """
                        SELECT gr_id, status FROM gr_requests
                        WHERE po_id = ? AND status NOT IN ('denied', 'finished')
                        """,
                        (po_id,),
                    ).fetchall()
                    if non_final_grs:
                        raise ConflictError(
                            f"Cannot finish PO: {len(non_final_grs)} GR(s) not in final state. "
                            "Approve, deny or finish all GRs first."
                        )

                timestamp = utc_now()
                after = _finish_po_in_transaction(conn, po_id, current_user, timestamp)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def recall_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Recall PO back to draft. Only the PO/SC owner or admin can recall, and only from active.
    Requires that the PO has no non-draft GRs (or non-draft call-off SCs for FC POs)."""

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]
        if sc_id:
            sc = lookup_conn.execute(
                "select status, requester_id from sc_records where sc_id = ?",
                (sc_id,),
            ).fetchone()
            if sc is None:
                raise NotFound(f"SC {sc_id} not found")
            if current_user.get("role") != "admin" and sc["requester_id"] != current_user["user_id"]:
                raise PermissionDenied("Only the SC requester or admin can recall POs")
            if sc["status"] == "finished":
                raise ConflictError("Finished SC cannot be edited")
        else:
            if current_user["role"] != "admin" and po["requester_id"] != current_user["user_id"]:
                raise PermissionDenied("Only the PO requester can recall POs")

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"
    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)

                if before["status"] != "active":
                    raise ConflictError("Only active PO can be recalled back to draft")

                # Effective FC type check
                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"

                if is_fc:
                    non_draft_calloffs = conn.execute(
                        "select count(*) from sc_records where calloff_po_id = ? and status != 'draft'",
                        (po_id,),
                    ).fetchone()[0]
                    if non_draft_calloffs > 0:
                        raise ConflictError("Cannot recall PO(FC): non-draft call-off SCs exist")
                else:
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
                    sc_id=before["sc_id"],
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=after,
                )
                if sc_id:
                    sc_requester = conn.execute(
                        "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                else:
                    sc_requester = None
                notification_service.queue_status_change(
                    conn, "po", po_id, "recall",
                    {"requester_id": sc_requester["requester_id"]} if sc_requester else {"requester_id": before["requester_id"]},
                    current_user
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return after


def delete_po(config: AppConfig, current_user: dict, po_id: str) -> dict:
    """Delete a draft PO and its GRs/attachments. Admin or PO/SC owner."""
    require_requester_or_admin(current_user)

    with connect(config) as lookup_conn:
        po = _get_po_or_raise(lookup_conn, po_id)
        sc_id = po["sc_id"]

    lock_key = f"sc:{sc_id}" if sc_id else f"po:{po_id}"
    with LeaseLock(config.lock_dir, lock_key, current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_po_or_raise(conn, po_id)
                if before["status"] != "draft":
                    raise ConflictError("Only draft PO can be deleted")

                # FC check (effective FC type)
                is_fc = before.get("request_type") == "FC"
                if not is_fc and sc_id:
                    parent_sc = conn.execute(
                        "select request_type from sc_records where sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    is_fc = parent_sc and parent_sc["request_type"] == "FC"
                if is_fc:
                    calloff_exists = conn.execute(
                        "select 1 from sc_records where calloff_po_id = ? limit 1",
                        (po_id,),
                    ).fetchone()
                    if calloff_exists:
                        raise ConflictError("Cannot delete PO(FC) with existing call-off SCs")

                # Permission check
                if sc_id:
                    sc = conn.execute(
                        "SELECT requester_id FROM sc_records WHERE sc_id = ?",
                        (before["sc_id"],),
                    ).fetchone()
                    if current_user["role"] != "admin" and (
                        sc is None or sc["requester_id"] != current_user["user_id"]
                    ):
                        raise PermissionDenied("Only the SC owner or admin can delete")
                else:
                    if current_user["role"] != "admin" and before["requester_id"] != current_user["user_id"]:
                        raise PermissionDenied("Only the PO owner or admin can delete")

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


def _validate_annual_report_year(year: str) -> tuple[str, str]:
    import re

    if not isinstance(year, str) or not re.fullmatch(r"\d{4}", year):
        raise ValidationError("year must be a 4-digit string")
    previous_year = str(int(year) - 1)
    return year, previous_year


def _annual_gr_year_expr() -> str:
    return (
        "case "
        "when status = 'finished' then substr(finished_at, 1, 4) "
        "when status = 'approved' then substr(approved_date, 1, 4) "
        "else null end"
    )


def get_annual_report_data(config: AppConfig, year: str, current_user: dict) -> list[dict]:
    """Return annual report rows for PO List export."""
    require_admin(current_user)
    selected_year, previous_year = _validate_annual_report_year(year)
    year_expr = _annual_gr_year_expr()

    with connect(config) as conn:
        po_rows = conn.execute(
            f"""
            with gr_totals as (
              select
                po_id,
                sum(case when report_year = ? then coalesce(con_value, 0) else 0 end) as previous_year_gr,
                sum(case when report_year = ? then coalesce(con_value, 0) else 0 end) as selected_year_gr,
                sum(case when report_year = ? then 1 else 0 end) as selected_year_count
              from (
                select po_id, con_value, {year_expr} as report_year
                from gr_requests
                where status in ('approved', 'finished')
              )
              where report_year is not null
              group by po_id
            )
            select
              'po' as row_type,
              po.sc_id as _sc_id,
              coalesce(u.user_name, po.requester_id, '') as requester,
              coalesce(sc.sc_no, '') as sc_no,
              coalesce(po.po_no, '') as po_no,
              coalesce(sc.description, '') as short_text,
              sc.sc_amount as sc_amount,
              po.po_amount as po_amount,
              coalesce(gr.previous_year_gr, 0) as previous_year_gr,
              '' as previous_year_provision,
              coalesce(gr.selected_year_gr, 0) as selected_year_gr,
              '' as selected_year_to_be_gr,
              '' as selected_year_fc_gr,
              '' as remark
            from pos po
            left join sc_records sc on sc.sc_id = po.sc_id
            left join users u on u.user_id = po.requester_id
            left join gr_totals gr on gr.po_id = po.po_id
            where
              (sc.status = 'approved' and po.status in ('active', 'finished'))
              or coalesce(gr.selected_year_count, 0) > 0
              or po.status = 'active'
              or (po.status = 'finished' and substr(po.finished_at, 1, 4) = ?)
            order by coalesce(sc.sc_no, ''), coalesce(po.po_no, ''), po.po_id
            """,
            (previous_year, selected_year, selected_year, selected_year),
        ).fetchall()

        qualifying_sc_ids = {
            row["_sc_id"] for row in po_rows if row["_sc_id"] not in (None, "")
        }

        sc_rows = conn.execute(
            """
            select
              'sc' as row_type,
              sc.sc_id as _sc_id,
              coalesce(u.user_name, sc.requester_id, '') as requester,
              coalesce(sc.sc_no, '') as sc_no,
              '' as po_no,
              coalesce(sc.description, '') as short_text,
              sc.sc_amount as sc_amount,
              '' as po_amount,
              '' as previous_year_gr,
              '' as previous_year_provision,
              '' as selected_year_gr,
              '' as selected_year_to_be_gr,
              '' as selected_year_fc_gr,
              '' as remark
            from sc_records sc
            left join users u on u.user_id = sc.requester_id
            where sc.status = 'approved'
            order by coalesce(sc.sc_no, ''), sc.sc_id
            """
        ).fetchall()

    result: list[dict] = []
    for row in po_rows:
        item = dict(row)
        item.pop("_sc_id", None)
        result.append(item)

    for row in sc_rows:
        item = dict(row)
        sc_id = item.pop("_sc_id", None)
        if sc_id not in qualifying_sc_ids:
            result.append(item)

    return result
