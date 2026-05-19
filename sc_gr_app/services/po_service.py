from datetime import datetime, timezone
from decimal import Decimal

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ConflictError, NotFound, ValidationError
from sc_gr_app.rbac import require_requester_or_admin
from sc_gr_app.services.audit_service import write_audit_log
from sc_gr_app.services.budget_service import compute_sc_budget_decimal
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("po_id", "sc_id", "vendor_id", "po_amount")
SUPPORTED_STATUSES = {"po_pending", "po_approved", "finished"}


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
    if number <= 0:
        raise ValidationError(f"{field} must be positive")
    return number


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_po(conn, po_id: str) -> dict:
    return _row_to_dict(
        conn.execute("select * from pos where po_id = ?", (po_id,)).fetchone()
    )


def create_po(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    po_amount = _positive_number(data["po_amount"], "po_amount")
    status = data.get("status", "po_pending")
    if status not in SUPPORTED_STATUSES:
        raise ValidationError("status is invalid")

    sc_id = data["sc_id"]
    po_id = data["po_id"]
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
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    return created
