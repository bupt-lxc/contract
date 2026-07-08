"""Bulk import service for SC, PO, GR records with direct status writes."""
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.lock_service import LeaseLock
from sc_gr_app.services.record_service import write_operation_record

SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_sc_id(conn, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"SC-{machine_id}-{today}-%"
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


def _generate_po_id(conn, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"PO-{machine_id}-{today}-%"
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


def _generate_gr_id(conn, machine_id: str) -> str:
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    pattern = f"GR-{machine_id}-{today}-%"
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


def _is_template_meta_row(row: dict, id_field: str) -> bool:
    """Check if this is a template meta row (hint or sample) that should be skipped."""
    val = row.get(id_field, "").strip()
    if val == "[EXAMPLE]":
        return True
    # Hint rows have ID values that look like instructions rather than real IDs.
    # Real IDs are empty, alphanumeric+hyphens, or match the format XX-NNNNNNN-NNNNNNNN-NNN.
    # Hint text (like "Optional (auto-generated...)") contains spaces and parens.
    if " " in val or "(" in val:
        return True
    return False


def _validate_sc_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all SC rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "sc_id"):
            continue
        for field in ["sc_no", "sc_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in SC_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
    return errors


def import_scs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import SC records with direct status writes.

    ID fields are optional and auto-generated when empty.
    Duplicate IDs are silently skipped.
    Sample rows (ID = [EXAMPLE]) are silently skipped.
    """
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_sc_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "sc_id"):
                        continue
                    sc_id = (row.get("sc_id") or "").strip()
                    if sc_id:
                        exists = conn.execute(
                            "SELECT 1 FROM sc_records WHERE sc_id = ?", (sc_id,)
                        ).fetchone()
                        if exists:
                            skipped_duplicate += 1
                            continue
                    else:
                        sc_id = _generate_sc_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          created_by, created_at, updated_at, asset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
                        (
                            sc_id,
                            row.get("sc_no"),
                            row.get("requester_id") or current_user["user_id"],
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
                        object_id=sc_id,
                        sc_id=sc_id,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise


PO_IMPORT_ALLOWED_STATUSES = {"active", "finished"}


def _validate_po_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all PO rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "po_id"):
            continue
        for field in ["sc_id", "po_no", "po_amount", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in PO_IMPORT_ALLOWED_STATUSES:
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
    return errors


def import_pos(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import PO records with direct status writes.

    ID fields are optional and auto-generated when empty.
    Duplicate IDs are silently skipped.
    Sample rows (ID = [EXAMPLE]) are silently skipped.
    """
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_po_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "po_id"):
                        continue
                    po_id = (row.get("po_id") or "").strip()
                    if po_id:
                        exists = conn.execute(
                            "SELECT 1 FROM pos WHERE po_id = ?", (po_id,)
                        ).fetchone()
                        if exists:
                            skipped_duplicate += 1
                            continue
                    else:
                        po_id = _generate_po_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id,
                            row["sc_id"],
                            row.get("vendor_id"),
                            row.get("po_no"),
                            row.get("requester_id") or current_user["user_id"],
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
                        object_id=po_id,
                        sc_id=row["sc_id"],
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise


GR_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}


def _validate_gr_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all GR rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "gr_id"):
            continue
        # Resolve po_no to po_id if po_id is not provided directly
        if not row.get("po_id") and row.get("po_no"):
            po_row = conn.execute(
                "SELECT po_id FROM pos WHERE po_no = ?",
                (row["po_no"],),
            ).fetchone()
            if po_row:
                row["po_id"] = po_row["po_id"]
        for field in ["po_id", "gr_no", "con_value", "status"]:
            if not row.get(field):
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = row.get("status", "")
        if status and status not in GR_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("po_id"):
            exists = conn.execute(
                "SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "po_id", "message": f"PO {row['po_id']} not found"})
    return errors


def preview_sc_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate SC rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "sc_id"):
                continue
            errors_list = []
            for field in ["sc_no", "sc_amount", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in SC_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("requester_id"):
                exists = conn.execute(
                    "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"User {row['requester_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview


def preview_po_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate PO rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "po_id"):
                continue
            errors_list = []
            for field in ["sc_id", "po_no", "po_amount", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in PO_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("sc_id"):
                exists = conn.execute(
                    "SELECT 1 FROM sc_records WHERE sc_id = ?", (row["sc_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"SC {row['sc_id']} not found")
            if row.get("vendor_id"):
                exists = conn.execute(
                    "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"Vendor {row['vendor_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview


def preview_gr_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate GR rows without inserting. Returns rows annotated with _errors and _valid."""
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "gr_id"):
                continue
            errors_list = []
            # Resolve po_no to po_id if po_id is not provided directly
            if not row.get("po_id") and row.get("po_no"):
                po_row = conn.execute(
                    "SELECT po_id FROM pos WHERE po_no = ?",
                    (row["po_no"],),
                ).fetchone()
                if po_row:
                    row["po_id"] = po_row["po_id"]
            for field in ["po_id", "gr_no", "con_value", "status"]:
                if not row.get(field):
                    errors_list.append(f"{field} is required")
            status = row.get("status", "")
            if status and status not in GR_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            if row.get("po_id"):
                exists = conn.execute(
                    "SELECT 1 FROM pos WHERE po_id = ?", (row["po_id"],)
                ).fetchone()
                if not exists:
                    errors_list.append(f"PO {row['po_id']} not found")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)
    return preview

def import_grs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import GR records with direct status writes.

    ID fields are optional and auto-generated when empty.
    Duplicate IDs are silently skipped.
    Sample rows (ID = [EXAMPLE]) are silently skipped.
    """
    timestamp = utc_now()
    machine_id = current_user["machine_id"]
    with LeaseLock(config.lock_dir, "import:lock", machine_id):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                errors = _validate_gr_rows(conn, rows)
                if errors:
                    conn.rollback()
                    return {"ok": False, "errors": errors}

                imported = 0
                skipped_duplicate = 0
                for row in rows:
                    if _is_template_meta_row(row, "gr_id"):
                        continue
                    gr_id = (row.get("gr_id") or "").strip()
                    if gr_id:
                        exists = conn.execute(
                            "SELECT 1 FROM gr_requests WHERE gr_id = ?", (gr_id,)
                        ).fetchone()
                        if exists:
                            skipped_duplicate += 1
                            continue
                    else:
                        gr_id = _generate_gr_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO gr_requests (
                          gr_id, po_id, gr_no, requester_id,
                          estimated_amount, con_value, status, remark, tax_rate,
                          gross_cost, goods_service_description, confirmation_name,
                          delivery_from, delivery_to, last_delivery,
                          created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            gr_id,
                            row["po_id"],
                            row.get("gr_no"),
                            row.get("requester_id") or current_user["user_id"],
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
                        object_id=gr_id,
                        sc_id=None,
                        operator_id=current_user["user_id"],
                        machine_id=machine_id,
                        before=None,
                        after=dict(row),
                    )
                    imported += 1

                conn.commit()
                return {"ok": True, "count": imported, "skipped_duplicate": skipped_duplicate}
            except Exception:
                conn.rollback()
                raise
