"""Bulk import service for SC, PO, GR records with direct status writes."""
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.lock_service import LeaseLock
from sc_gr_app.services.record_service import write_operation_record

SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
]


def parse_date(value: str) -> str | None:
    """Parse a date string into YYYY-MM-DD format. Returns None if unparseable."""
    if not value or not str(value).strip():
        return None
    value = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


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
        if _is_template_meta_row(row, "sc_no"):
            continue
        for field in ["sc_no", "sc_amount", "status"]:
            val = row.get(field)
            if val is None or str(val).strip() == "":
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = str(row.get("status", "")).strip()
        if status and status not in SC_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
        calloff_po_id = row.get("calloff_po_id")
        if calloff_po_id:
            po_exists = conn.execute(
                "select 1 from pos po join sc_records sc on sc.sc_id = po.sc_id "
                "where po.po_id = ? and sc.request_type = 'FC'",
                (calloff_po_id,),
            ).fetchone()
            if not po_exists:
                errors.append({"row": i, "field": "calloff_po_id", "message": f"calloff_po_id {calloff_po_id} is not a valid FC PO"})
        # Validate vendor_ids if provided
        vendor_ids = str(row.get("vendor_id", "")).strip()
        if vendor_ids:
            for vid in vendor_ids.split(","):
                vid = vid.strip()
                if vid:
                    v = conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (vid,)).fetchone()
                    if not v:
                        errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {vid} not found"})

    # DB-level SC NO uniqueness check
    sc_nos_in_file = [r["sc_no"].strip() for r in rows if r.get("sc_no") and not _is_template_meta_row(r, "sc_no")]
    if sc_nos_in_file:
        placeholders = ",".join(["?"] * len(sc_nos_in_file))
        dupes = conn.execute(
            f"SELECT sc_no, COUNT(*) as cnt FROM sc_records WHERE sc_no IN ({placeholders}) GROUP BY sc_no HAVING COUNT(*) > 1",
            sc_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate SC NO found in database: {', '.join(d['sc_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
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
                    if _is_template_meta_row(row, "sc_no"):
                        continue
                    sc_no = str(row.get("sc_no", "")).strip()
                    # Check if sc_no already exists in DB
                    exists = conn.execute(
                        "SELECT 1 FROM sc_records WHERE sc_no = ?", (sc_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    sc_id = (row.get("sc_id") or "").strip()
                    if not sc_id:
                        sc_id = _generate_sc_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO sc_records (
                          sc_id, sc_no, requester_id, request_type, cost_center,
                          sc_amount, service_period_start, service_period_end,
                          status, description, currency, internal_system_number,
                          created_by, created_at, updated_at, asset, asset_nums
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            sc_id,
                            sc_no,
                            row.get("requester_id") or current_user["user_id"],
                            row.get("request_type"),
                            row.get("cost_center"),
                            float(row["sc_amount"]) if row.get("sc_amount") else None,
                            parse_date(row.get("service_period_start")),
                            parse_date(row.get("service_period_end")),
                            row["status"],
                            row.get("description"),
                            row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            current_user["user_id"],
                            timestamp,
                            timestamp,
                            row.get("asset", "N"),
                            row.get("asset_nums"),
                        ),
                    )
                    # Insert sc_vendors if vendor_id provided (comma-separated)
                    vendor_ids = str(row.get("vendor_id", "")).strip()
                    if vendor_ids:
                        for vid in vendor_ids.split(","):
                            vid = vid.strip()
                            if vid:
                                conn.execute(
                                    "INSERT OR IGNORE INTO sc_vendors (sc_id, vendor_id) VALUES (?, ?)",
                                    (sc_id, vid),
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
                            parse_date(row.get("contract_from")),
                            parse_date(row.get("contract_to")),
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
        for field in ["po_id", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
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
            if _is_template_meta_row(row, "sc_no"):
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
            # Validate vendor_ids if provided
            vendor_ids = str(row.get("vendor_id", "")).strip()
            if vendor_ids:
                for vid in vendor_ids.split(","):
                    vid = vid.strip()
                    if vid:
                        v = conn.execute("SELECT 1 FROM vendors WHERE vendor_id = ?", (vid,)).fetchone()
                        if not v:
                            errors_list.append(f"Vendor {vid} not found")

            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)

        # File-level SC NO duplicate detection
        sc_no_counts = {}
        for r in preview:
            sc_no = (r.get("sc_no") or "").strip()
            if sc_no:
                sc_no_counts[sc_no] = sc_no_counts.get(sc_no, 0) + 1
        for r in preview:
            sc_no = (r.get("sc_no") or "").strip()
            if sc_no and sc_no_counts.get(sc_no, 0) > 1:
                r["_errors"].append(f"SC NO '{sc_no}' appears {sc_no_counts[sc_no]} times in this file")
                r["_valid"] = False

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
            for field in ["po_id", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
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
                            parse_date(row.get("delivery_from")),
                            parse_date(row.get("delivery_to")),
                            parse_date(row.get("last_delivery")),
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
