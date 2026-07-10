"""Bulk import service for SC, PO, GR records with direct status writes."""
import re
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.lock_service import LeaseLock
from sc_gr_app.services.record_service import write_operation_record

SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}
LEGACY_REQUEST_TYPE_MAP = {
    "material": "new",
    "service": "new",
    "fixed_asset": "new",
}


def _normalize_request_type(value):
    if value in (None, ""):
        return value
    return LEGACY_REQUEST_TYPE_MAP.get(value, value)


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
    for field in (id_field, "sc_no", "po_no", "gr_no"):
        val = str(row.get(field) or "").strip()
        if val == "[EXAMPLE]":
            return True
        # Hint rows have ID values that look like instructions rather than real IDs.
        # Hint text (like "Optional (auto-generated...)") contains spaces and parens.
        if field == id_field and (" " in val or "(" in val):
            return True
    return False


def _resolve_po_sc_id(conn, row: dict) -> str | None:
    """Resolve an import row's SC NO into sc_id when no sc_id is provided."""
    if row.get("sc_id"):
        return None
    sc_no = (row.get("sc_no") or "").strip()
    if not sc_no:
        return None
    matches = conn.execute(
        "SELECT sc_id FROM sc_records WHERE sc_no = ? ORDER BY sc_id",
        (sc_no,),
    ).fetchall()
    if len(matches) == 1:
        row["sc_id"] = matches[0]["sc_id"]
        return None
    if len(matches) == 0:
        return f"SC NO {sc_no} not found"
    return f"SC NO {sc_no} is ambiguous"


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
        sc_no = (row.get("sc_no") or "").strip()
        if sc_no:
            existing = conn.execute(
                "SELECT COUNT(*) FROM sc_records WHERE sc_no = ?",
                (sc_no,),
            ).fetchone()[0]
            if existing:
                raise ValidationError(f"Duplicate SC NO: {sc_no}")
        request_type = _normalize_request_type(row.get("request_type"))
        if request_type and request_type not in ("FC", "call_off", "new"):
            errors.append({"row": i, "field": "request_type", "message": "request_type is invalid"})
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
                # Normalize: ISN "N/A" means no parent PO -> not a call-off
                for row in rows:
                    if (row.get("request_type") == "call_off"
                            and str(row.get("internal_system_number", "")).strip().upper() == "N/A"):
                        row["request_type"] = "new"
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
                          service_scope, calloff_po_id, asset_nums,
                          created_by, created_at, updated_at, asset
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'N')""",
                        (
                            sc_id,
                            row.get("sc_no"),
                            row.get("requester_id") or current_user["user_id"],
                            _normalize_request_type(row.get("request_type")),
                            row.get("cost_center"),
                            float(row["sc_amount"]) if row.get("sc_amount") else None,
                            row.get("service_period_start"),
                            row.get("service_period_end"),
                            row["status"],
                            row.get("description"),
                            row.get("currency", "CNY"),
                            row.get("internal_system_number"),
                            row.get("service_scope"),
                            row.get("calloff_po_id"),
                            row.get("asset_nums"),
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
        sc_error = _resolve_po_sc_id(conn, row)
        if not row.get("sc_id") and not row.get("sc_no") and row.get("request_type") != "FC":
            errors.append({"row": i, "field": "sc_no", "message": "sc_no is required"})
        elif sc_error:
            errors.append({"row": i, "field": "sc_no", "message": sc_error})
        for field in ["po_no", "po_amount", "status"]:
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
                          purchaser, request_type, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                            row.get("request_type"),
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

# Column header aliases for bilingual (EN/CN) import templates
_SC_COLUMN_ALIASES = {
    "sc_id": ["SC ID", "sc_id"],
    "sc_no": ["SC NO", "sc_no"],
    "requester_id": ["Requester ID", "requester_id"],
    "request_type": ["Request Type", "request_type"],
    "cost_center": ["Cost Center", "cost_center"],
    "sc_amount": ["SC Amount", "sc_amount"],
    "service_period_start": ["Service Period Start", "service_period_start"],
    "service_period_end": ["Service Period End", "service_period_end"],
    "status": ["Status", "status"],
    "description": ["Description", "description"],
    "currency": ["Currency", "currency"],
    "internal_system_number": ["Internal System Number", "internal_system_number"],
    "service_scope": ["Service Scope", "service_scope"],
    "calloff_po_id": ["Call-off PO ID", "calloff_po_id"],
    "asset_nums": ["Asset Nums", "asset_nums"],
    "asset": ["Asset", "asset"],
}

_PO_COLUMN_ALIASES = {
    "po_id": ["PO ID", "po_id"],
    "sc_id": ["SC ID", "sc_id"],
    "vendor_id": ["Vendor ID", "vendor_id"],
    "po_no": ["PO NO", "po_no"],
    "requester_id": ["Requester ID", "requester_id"],
    "po_amount": ["PO Amount", "po_amount"],
    "status": ["Status", "status"],
    "contract_from": ["Contract From", "contract_from"],
    "contract_to": ["Contract To", "contract_to"],
    "contract_no": ["Contract NO", "contract_no"],
    "payment_frequency": ["Payment Frequency", "payment_frequency"],
    "contract_pos": ["Contract POs", "contract_pos"],
    "contract_type": ["Contract Type", "contract_type"],
    "cost_center": ["Cost Center", "cost_center"],
    "purchaser": ["Purchaser", "purchaser"],
}

_GR_COLUMN_ALIASES = {
    "gr_id": ["GR ID", "gr_id"],
    "po_id": ["PO ID", "po_id"],
    "po_no": ["PO NO", "po_no"],
    "gr_no": ["GR NO", "gr_no"],
    "requester_id": ["Requester ID", "requester_id"],
    "estimated_amount": ["Estimated Amount", "estimated_amount"],
    "con_value": ["Con Value", "con_value"],
    "status": ["Status", "status"],
    "remark": ["Remark", "remark"],
    "tax_rate": ["Tax Rate", "tax_rate"],
    "gross_cost": ["Gross Cost", "gross_cost"],
    "goods_service_description": ["Goods/Service Description", "goods_service_description"],
    "confirmation_name": ["Confirmation Name", "confirmation_name"],
    "last_delivery": ["Last Delivery", "last_delivery"],
    "is_cancellation": ["Is Cancellation", "is_cancellation", "是否取消类型"],
}

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d.%m.%Y",
    "%m/%d/%Y",
    "%m-%d-%Y",
    "%d/%m/%Y",
    "%Y%m%d",
]


def parse_date(value: str) -> str | None:
    """Parse a date string into ISO format (YYYY-MM-DD). Returns None if unparseable."""
    if not value:
        return None
    value = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def _normalize_import_header(header: str) -> str | None:
    """Map a raw header name to its canonical key, or None if unrecognized."""
    h = header.strip()
    # Direct match against all aliases
    for canonical, aliases in {**_SC_COLUMN_ALIASES, **_PO_COLUMN_ALIASES, **_GR_COLUMN_ALIASES}.items():
        if h in aliases:
            return canonical
    # Fuzzy match: remove spaces/underscores and compare case-insensitively
    normalized = re.sub(r"[ _-]", "", h).lower()
    for canonical, aliases in {**_SC_COLUMN_ALIASES, **_PO_COLUMN_ALIASES, **_GR_COLUMN_ALIASES}.items():
        for alias in aliases:
            if re.sub(r"[ _-]", "", alias).lower() == normalized:
                return canonical
    return None


def _map_import_columns(raw_headers: list[str], entity_aliases: dict) -> dict[str, int]:
    """Map raw header names to (canonical_key, column_index) using alias lookup."""
    mapping: dict[str, int] = {}
    for i, header in enumerate(raw_headers):
        canonical = _normalize_import_header(header)
        if canonical and canonical in entity_aliases:
            mapping[canonical] = i
    return mapping


def _validate_gr_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all GR rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "gr_id"):
            continue
        _resolve_gr_po_id(conn, row)
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
        # Validate is_cancellation
        is_canc = (row.get("is_cancellation") or "N").strip().upper()
        if is_canc not in ("Y", "N"):
            errors.append({"row": i, "field": "is_cancellation", "message": "is_cancellation must be Y or N"})
        # Cross-validate amounts against is_cancellation
        if is_canc == "Y":
            try:
                est = float(row["estimated_amount"]) if row.get("estimated_amount") else None
                if est is not None and est >= 0:
                    errors.append({"row": i, "field": "estimated_amount", "message": "Cancellation GR estimated_amount must be negative"})
            except (ValueError, TypeError):
                pass
            try:
                cv = float(row["con_value"]) if row.get("con_value") else None
                if cv is not None and cv > 0:
                    errors.append({"row": i, "field": "con_value", "message": "Cancellation GR con_value must be non-positive"})
            except (ValueError, TypeError):
                pass
        # Check GR NO uniqueness in DB
        gr_no = (row.get("gr_no") or "").strip()
        if gr_no:
            exists = conn.execute(
                "SELECT 1 FROM gr_requests WHERE gr_no = ?", (gr_no,)
            ).fetchone()
            if exists:
                errors.append({"row": i, "field": "gr_no", "message": f"GR NO {gr_no} already exists"})
    return errors


def _resolve_gr_po_id(conn, row: dict) -> None:
    """Resolve po_no to the current DB po_id, overriding stale imported po_id."""
    po_no = (row.get("po_no") or "").strip()
    if not po_no:
        return
    po_row = conn.execute(
        "SELECT po_id FROM pos WHERE po_no = ?",
        (po_no,),
    ).fetchone()
    if po_row:
        row["po_id"] = po_row["po_id"]


def _po_has_finished_gr(conn, po_id: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM gr_requests WHERE po_id = ? AND status = 'finished' LIMIT 1",
        (po_id,),
    ).fetchone()
    return row is not None


def _finish_po_gr_group(conn, po_id: str, timestamp: str) -> None:
    conn.execute(
        "UPDATE pos SET status = 'finished', updated_at = ? WHERE po_id = ?",
        (timestamp, po_id),
    )
    conn.execute(
        "UPDATE gr_requests SET status = 'finished', updated_at = ? WHERE po_id = ?",
        (timestamp, po_id),
    )


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
            sc_no = (row.get("sc_no") or "").strip()
            if sc_no:
                existing = conn.execute(
                    "SELECT COUNT(*) FROM sc_records WHERE sc_no = ?",
                    (sc_no,),
                ).fetchone()[0]
                if existing:
                    errors_list.append(f"Duplicate SC NO: {sc_no}")
            request_type = _normalize_request_type(row.get("request_type"))
            if request_type and request_type not in ("FC", "call_off", "new"):
                errors_list.append("request_type is invalid")
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
            sc_error = _resolve_po_sc_id(conn, row)
            if not row.get("sc_id") and not row.get("sc_no") and row.get("request_type") != "FC":
                errors_list.append("sc_no is required")
            elif sc_error:
                errors_list.append(sc_error)
            for field in ["po_no", "po_amount", "status"]:
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
            _resolve_gr_po_id(conn, row)
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
            # Validate is_cancellation
            is_canc = (row.get("is_cancellation") or "N").strip().upper()
            if is_canc not in ("Y", "N"):
                errors_list.append("is_cancellation must be Y or N")
            if is_canc == "Y":
                try:
                    est = float(row["estimated_amount"]) if row.get("estimated_amount") else None
                    if est is not None and est >= 0:
                        errors_list.append("Cancellation GR estimated_amount must be negative")
                except (ValueError, TypeError):
                    pass
                try:
                    cv = float(row["con_value"]) if row.get("con_value") else None
                    if cv is not None and cv > 0:
                        errors_list.append("Cancellation GR con_value must be non-positive")
                except (ValueError, TypeError):
                    pass
            # Check GR NO uniqueness in DB
            gr_no = (row.get("gr_no") or "").strip()
            if gr_no:
                exists = conn.execute(
                    "SELECT 1 FROM gr_requests WHERE gr_no = ?", (gr_no,)
                ).fetchone()
                if exists:
                    errors_list.append(f"GR NO {gr_no} already exists")
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
                    po_id = row["po_id"]
                    finish_group = (
                        row.get("status") == "finished"
                        or _po_has_finished_gr(conn, po_id)
                    )
                    if finish_group:
                        row["status"] = "finished"
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
                          last_delivery, is_cancellation,
                          created_by, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            gr_id,
                            po_id,
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
                            row.get("last_delivery"),
                            row.get("is_cancellation", "N"),
                            current_user["user_id"],
                            timestamp,
                        ),
                    )
                    if finish_group:
                        _finish_po_gr_group(conn, po_id, timestamp)
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
