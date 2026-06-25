"""Bulk import service for SC, PO, GR records with direct status writes."""
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.lock_service import LeaseLock
from sc_gr_app.services.record_service import write_operation_record

SC_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "denied", "closed"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_sc_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all SC rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        for field in ["sc_id", "requester_id", "sc_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in SC_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
        if row.get("sc_id"):
            exists = conn.execute(
                "SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)
            ).fetchone()
            if exists:
                errors.append({"row": i, "field": "sc_id", "message": f"SC {row['sc_id']} already exists"})
    return errors


def import_scs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import SC records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_sc_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          created_by, created_at, updated_at, asset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
                        (
                            row["sc_id"],
                            row.get("sc_no"),
                            row["requester_id"],
                            row.get("request_type"),
                            row.get("cost_center"),
                            float(row["sc_amount"]) if row.get("sc_amount") else None,
                            row.get("service_period_start"),
                            row.get("service_period_end"),
                            row["status"],
                            row.get("description"),
                            row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            current_user["user_id"],
                            timestamp,
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_sc",
                        object_type="sc",
                        object_id=row["sc_id"],
                        sc_id=row["sc_id"],
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise


PO_ALLOWED_STATUSES = {"draft", "activing", "finished"}


def _validate_po_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all PO rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        for field in ["po_id", "sc_id", "po_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in PO_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("sc_id"):
            exists = conn.execute(
                "SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "sc_id", "message": f"SC {row['sc_id']} not found"})
        if row.get("vendor_id"):
            exists = conn.execute(
                "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {row['vendor_id']} not found"})
        if row.get("po_id"):
            exists = conn.execute(
                "SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)
            ).fetchone()
            if exists:
                errors.append({"row": i, "field": "po_id", "message": f"PO {row['po_id']} already exists"})
    return errors


def import_pos(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import PO records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_po_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, activing_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["po_id"],
                            row["sc_id"],
                            row.get("vendor_id"),
                            row.get("po_no"),
                            row.get("requester_id"),
                            float(row["po_amount"]) if row.get("po_amount") else None,
                            row.get("status", "draft"),
                            row.get("contract_from"),
                            row.get("contract_to"),
                            row.get("contract_no"),
                            row.get("payment_frequency"),
                            row.get("contract_pos"),
                            row.get("contract_type"),
                            row.get("cost_center"),
                            row.get("purchaser"),
                            None if row.get("status") == "draft" else timestamp,
                            timestamp,
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_po",
                        object_type="po",
                        object_id=row["po_id"],
                        sc_id=row["sc_id"],
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise


GR_ALLOWED_STATUSES = {"draft", "manager_confirm", "pending", "approved", "cancelled"}


def _validate_gr_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all GR rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        for field in ["gr_id", "po_id", "estimated_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in GR_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("po_id"):
            exists = conn.execute(
                "SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "po_id", "message": f"PO {row['po_id']} not found"})
        if row.get("gr_id"):
            exists = conn.execute(
                "SELECT 1 FROM gr_requests WHERE gr_id = ?", (row["gr_id"],)
            ).fetchone()
            if exists:
                errors.append({"row": i, "field": "gr_id", "message": f"GR {row['gr_id']} already exists"})
    return errors


def import_grs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import GR records with direct status writes."""
    timestamp = utc_now()
    with LeaseLock(config.lock_dir, "import:lock", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_gr_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                for row in rows:
                    conn.execute(
                        """INSERT INTO gr_requests (
                          gr_id, po_id, gr_no, requester_id,
                          estimated_amount, con_value, status, remark, tax_rate,
                          gross_cost, goods_service_description, confirmation_name,
                          delivery_from, delivery_to, last_delivery,
                          created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            row["gr_id"],
                            row["po_id"],
                            row.get("gr_no"),
                            row.get("requester_id"),
                            float(row["estimated_amount"]) if row.get("estimated_amount") else None,
                            float(row["con_value"]) if row.get("con_value") else None,
                            row.get("status", "draft"),
                            row.get("remark"),
                            float(row["tax_rate"]) if row.get("tax_rate") else None,
                            float(row["gross_cost"]) if row.get("gross_cost") else None,
                            row.get("goods_service_description"),
                            row.get("confirmation_name"),
                            row.get("delivery_from"),
                            row.get("delivery_to"),
                            row.get("last_delivery"),
                            current_user["user_id"],
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_gr",
                        object_type="gr",
                        object_id=row["gr_id"],
                        sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=current_user["machine_id"],
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported}
            except Exception:
                conn.rollback()
                raise
