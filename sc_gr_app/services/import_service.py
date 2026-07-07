"""Bulk import service for SC, PO, GR records with direct status writes."""
import re
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.services.lock_service import LeaseLock
from sc_gr_app.services.record_service import write_operation_record

SC_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}

# Column aliases: internal field → recognized header names (English + Chinese)
_SC_COLUMN_ALIASES: dict[str, list[str]] = {
    "sc_id":                  ["SC ID", "sc_id", "合同ID"],
    "sc_no":                  ["SC NO", "SC Number", "Contract NO", "sc_no", "合同编号", "合同号"],
    "vendor_id":              ["Vendor ID", "Supplier ID", "vendor_id", "供应商ID"],
    "requester_id":           ["Requester ID", "requester_id", "申请人ID", "申请人"],
    "request_type":           ["Request Type", "request_type", "类型", "采购类型", "请求类型"],
    "cost_center":            ["Cost Center", "cost_center", "成本中心"],
    "sc_amount":              ["SC Amount", "Amount", "sc_amount", "合同金额", "金额"],
    "service_period_start":   ["Service Period Start", "Start Date", "service_period_start", "服务开始日期", "开始日期"],
    "service_period_end":     ["Service Period End", "End Date", "service_period_end", "服务结束日期", "结束日期"],
    "status":                 ["Status", "status", "状态"],
    "description":            ["Description", "description", "描述", "备注"],
    "currency":               ["Currency", "currency", "币种", "货币"],
    "internal_system_number": ["Internal System Number", "internal_system_number", "内部系统编号"],
    "calloff_po_id":          ["Call-off PO ID", "FC PO ID", "calloff_po_id"],
    "asset":                  ["Asset", "asset", "资产"],
    "asset_nums":             ["Asset Nums", "asset_nums", "资产数量"],
    "service_scope":          ["Service Scope", "service_scope", "服务范围"],
}

_PO_COLUMN_ALIASES: dict[str, list[str]] = {
    "po_id":             ["PO ID", "po_id", "采购订单ID"],
    "sc_no":             ["SC NO", "SC Number", "sc_no", "合同编号", "合同号"],
    "vendor_id":         ["Vendor ID", "Supplier ID", "vendor_id", "供应商ID"],
    "po_no":             ["PO NO", "PO Number", "po_no", "采购订单号", "采购订单编号"],
    "requester_id":      ["Requester ID", "requester_id", "申请人ID", "申请人"],
    "request_type":      ["Request Type", "request_type", "类型", "请求类型"],
    "po_amount":         ["PO Amount", "Amount", "po_amount", "订单金额", "金额"],
    "status":            ["Status", "status", "状态"],
    "contract_from":     ["Contract From", "Start Date", "contract_from", "合同开始日期", "开始日期"],
    "contract_to":       ["Contract To", "End Date", "contract_to", "合同结束日期", "结束日期"],
    "contract_no":       ["Contract NO", "Contract Number", "contract_no", "合同编号", "合同号"],
    "payment_frequency": ["Payment Frequency", "payment_frequency", "付款频率"],
    "contract_pos":      ["Contract POS", "contract_pos", "合同订单"],
    "contract_type":     ["Contract Type", "contract_type", "合同类型"],
    "cost_center":       ["Cost Center", "cost_center", "成本中心"],
    "purchaser":         ["Purchaser", "purchaser", "采购员", "采购人"],
}

_GR_COLUMN_ALIASES: dict[str, list[str]] = {
    "po_no":                     ["PO NO", "PO Number", "po_no", "采购订单号", "采购订单编号"],
    "gr_no":                     ["GR NO", "GR Number", "gr_no", "收货编号", "收货编号"],
    "requester_id":              ["Requester ID", "requester_id", "申请人ID", "申请人"],
    "estimated_amount":          ["Estimated Amount", "estimated_amount", "预估金额", "估计金额"],
    "con_value":                 ["Con Value", "con_value", "合同价值"],
    "status":                    ["Status", "status", "状态"],
    "remark":                    ["Remark", "remark", "备注"],
    "tax_rate":                  ["Tax Rate", "tax_rate", "税率"],
    "gross_cost":                ["Gross Cost", "gross_cost", "总成本"],
    "goods_service_description": ["Goods/Service Description", "goods_service_description", "商品/服务描述", "货物/服务描述"],
    "confirmation_name":         ["Confirmation Name", "confirmation_name", "确认人", "确认人"],
    "delivery_from":             ["Delivery From", "delivery_from", "交付开始", "开始日期"],
    "delivery_to":               ["Delivery To", "delivery_to", "交付结束", "结束日期"],
    "last_delivery":             ["Last Delivery", "last_delivery", "最后交付"],
}


def _normalize_import_header(h: str) -> str:
    """Normalize header text for fuzzy matching: lowercase, strip parentheses,
    collapse whitespace and underscores into single underscores."""
    h = h.strip().lower()
    h = re.sub(r'[()（）]', '', h)
    h = re.sub(r'[\s_]+', '_', h)
    return h.strip('_')


def _map_import_columns(rows: list[dict], aliases: dict[str, list[str]]) -> list[dict]:
    """Map incoming row keys to canonical field names using the alias table."""
    if not rows:
        return rows
    norm_to_field: dict[str, str] = {}
    for field_key, alias_list in aliases.items():
        for alias in alias_list:
            norm_to_field[_normalize_import_header(alias)] = field_key
    mapped = []
    for row in rows:
        new_row: dict = {}
        for key, value in row.items():
            norm_key = _normalize_import_header(str(key))
            canonical = norm_to_field.get(norm_key, key)
            new_row[canonical] = value
        mapped.append(new_row)
    return mapped

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
        # Validate request_type
        rt = str(row.get("request_type", "")).strip()
        if rt and rt not in ("FC", "call_off", "new"):
            errors.append({"row": i, "field": "request_type", "message": f"Invalid request_type: {rt}"})
        if row.get("requester_id"):
            exists = conn.execute(
                "SELECT 1 FROM users WHERE user_id = ?", (row["requester_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "requester_id", "message": f"User {row['requester_id']} not found"})
        calloff_po_id = row.get("calloff_po_id")
        if calloff_po_id:
            po_exists = conn.execute(
                "select 1 from pos po left join sc_records sc on sc.sc_id = po.sc_id "
                "where po.po_id = ? and (po.request_type = 'FC' or sc.request_type = 'FC')",
                (calloff_po_id,),
            ).fetchone()
            if not po_exists:
                errors.append({"row": i, "field": "calloff_po_id", "message": f"calloff_po_id {calloff_po_id} is not a valid FC PO"})
        # Validate service_scope if provided
        scope = str(row.get("service_scope", "")).strip()
        if scope:
            from sc_gr_app.services.vendor_service import SUPPORTED_SERVICE_SCOPES
            if scope not in SUPPORTED_SERVICE_SCOPES:
                errors.append({"row": i, "field": "service_scope", "message": f"Invalid service_scope: {scope}"})
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
    rows = _map_import_columns(rows, _SC_COLUMN_ALIASES)
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
                          status, description, currency, service_scope, internal_system_number,
                          calloff_po_id,
                          created_by, created_at, updated_at, asset, asset_nums
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
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
                            row.get("service_scope"),
                            row.get("internal_system_number"),
                            row.get("calloff_po_id"),
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


PO_IMPORT_ALLOWED_STATUSES = {"active", "finished", "draft"}


def _validate_po_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all PO rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "po_no"):
            continue
        request_type = str(row.get("request_type", "")).strip()
        sc_no = str(row.get("sc_no", "")).strip()
        # Required fields: po_no, po_amount, status are always required;
        # sc_no is required only for non-FC POs.
        for field in ["po_no", "po_amount", "status"]:
            val = row.get(field)
            if val is None or str(val).strip() == "":
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        # sc_no conditionally required
        if not sc_no and request_type != "FC":
            errors.append({"row": i, "field": "sc_no", "message": "sc_no is required for non-FC POs"})
        # Semantic validation for sc_no + request_type combinations
        if sc_no and request_type == "FC":
            errors.append({"row": i, "field": "sc_no", "message": "sc_no should be empty for independent FC POs (request_type='FC')"})
        # Status validation: draft only allowed for FC POs
        status = str(row.get("status", "")).strip()
        if status:
            if request_type == "FC":
                if status not in PO_IMPORT_ALLOWED_STATUSES:
                    errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
            else:
                if status not in {"active", "finished"}:
                    errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        # Resolve sc_no → sc_id
        if sc_no:
            sc_rows = conn.execute(
                "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
            ).fetchall()
            if len(sc_rows) == 0:
                errors.append({"row": i, "field": "sc_no", "message": f"SC with SC NO '{sc_no}' not found"})
            elif len(sc_rows) > 1:
                raise ValidationError(
                    f"Duplicate SC NO '{sc_no}' found in database ({len(sc_rows)} records). "
                    f"Please resolve duplicates before importing."
                )
        if row.get("vendor_id"):
            exists = conn.execute(
                "SELECT 1 FROM vendors WHERE vendor_id = ?", (row["vendor_id"],)
            ).fetchone()
            if not exists:
                errors.append({"row": i, "field": "vendor_id", "message": f"Vendor {row['vendor_id']} not found"})

    # DB-level PO NO uniqueness check
    po_nos_in_file = [r["po_no"].strip() for r in rows if r.get("po_no") and not _is_template_meta_row(r, "po_no")]
    if po_nos_in_file:
        placeholders = ",".join(["?"] * len(po_nos_in_file))
        dupes = conn.execute(
            f"SELECT po_no, COUNT(*) as cnt FROM pos WHERE po_no IN ({placeholders}) GROUP BY po_no HAVING COUNT(*) > 1",
            po_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate PO NO found in database: {', '.join(d['po_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
    return errors


def import_pos(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import PO records with direct status writes.

    ID fields are optional and auto-generated when empty.
    Duplicate NOs are silently skipped.
    Sample rows (ID = [EXAMPLE]) are silently skipped.
    """
    rows = _map_import_columns(rows, _PO_COLUMN_ALIASES)
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
                    if _is_template_meta_row(row, "po_no"):
                        continue
                    po_no = (row.get("po_no") or "").strip()
                    # Uniqueness check by po_no
                    exists = conn.execute(
                        "SELECT 1 FROM pos WHERE po_no = ?", (po_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    # Resolve sc_no → sc_id
                    sc_no = (row.get("sc_no") or "").strip()
                    sc_id = None
                    if sc_no:
                        sc_row = conn.execute(
                            "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
                        ).fetchone()
                        sc_id = sc_row["sc_id"]
                    po_id = _generate_po_id(conn, machine_id)
                    conn.execute(
                        """INSERT INTO pos (
                          po_id, sc_id, vendor_id, po_no, requester_id,
                          request_type,
                          po_amount, status, contract_from, contract_to, contract_no,
                          payment_frequency, contract_pos, contract_type, cost_center,
                          purchaser, active_date, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            po_id,
                            sc_id,
                            row.get("vendor_id"),
                            po_no,
                            row.get("requester_id") or current_user["user_id"],
                            row.get("request_type"),
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
                            parse_date(row.get("active_date")) if row.get("active_date") else None,
                            timestamp,
                            timestamp,
                        ),
                    )
                    write_operation_record(
                        conn,
                        action_type="import_po",
                        object_type="po",
                        object_id=po_id,
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


GR_IMPORT_ALLOWED_STATUSES = {"approved", "finished"}


def _validate_gr_rows(conn, rows: list[dict]) -> list[dict]:
    """Validate all GR rows. Returns list of error dicts."""
    errors = []
    for i, row in enumerate(rows, start=1):
        if _is_template_meta_row(row, "gr_no"):
            continue
        for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
            val = row.get(field)
            if val is None or str(val).strip() == "":
                errors.append({"row": i, "field": field, "message": f"{field} is required"})
        status = str(row.get("status", "")).strip()
        if status and status not in GR_IMPORT_ALLOWED_STATUSES:
            errors.append({"row": i, "field": "status", "message": f"Invalid status: {status}"})
        # Resolve po_no → po_id
        po_no = str(row.get("po_no", "")).strip()
        if po_no:
            po_rows = conn.execute(
                "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
            ).fetchall()
            if len(po_rows) == 0:
                errors.append({"row": i, "field": "po_no", "message": f"PO with PO NO '{po_no}' not found"})
            elif len(po_rows) > 1:
                raise ValidationError(
                    f"Duplicate PO NO '{po_no}' found in database ({len(po_rows)} records). "
                    f"Please resolve duplicates before importing."
                )

    # DB-level GR NO uniqueness check
    gr_nos_in_file = [r["gr_no"].strip() for r in rows if r.get("gr_no") and not _is_template_meta_row(r, "gr_no")]
    if gr_nos_in_file:
        placeholders = ",".join(["?"] * len(gr_nos_in_file))
        dupes = conn.execute(
            f"SELECT gr_no, COUNT(*) as cnt FROM gr_requests WHERE gr_no IN ({placeholders}) GROUP BY gr_no HAVING COUNT(*) > 1",
            gr_nos_in_file,
        ).fetchall()
        if dupes:
            raise ValidationError(
                f"Duplicate GR NO found in database: {', '.join(d['gr_no'] for d in dupes)}. "
                f"Please resolve duplicates before importing."
            )
    return errors


def preview_sc_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate SC rows without inserting. Returns rows annotated with _errors and _valid."""
    rows = _map_import_columns(rows, _SC_COLUMN_ALIASES)
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
    rows = _map_import_columns(rows, _PO_COLUMN_ALIASES)
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "po_no"):
                continue
            errors_list = []
            request_type = str(row.get("request_type", "")).strip()
            sc_no = str(row.get("sc_no", "")).strip()
            # Required fields: po_no, po_amount, status are always required;
            # sc_no is required only for non-FC POs.
            for field in ["po_no", "po_amount", "status"]:
                val = row.get(field)
                if val is None or str(val).strip() == "":
                    errors_list.append(f"{field} is required")
            # sc_no conditionally required
            if not sc_no and request_type != "FC":
                errors_list.append("sc_no is required for non-FC POs")
            # Semantic validation for sc_no + request_type combinations
            if sc_no and request_type == "FC":
                errors_list.append("sc_no should be empty for independent FC POs (request_type='FC')")
            # Status validation: draft only allowed for FC POs
            status = str(row.get("status", "")).strip()
            if status:
                if request_type == "FC":
                    if status not in PO_IMPORT_ALLOWED_STATUSES:
                        errors_list.append(f"Invalid status: {status}")
                else:
                    if status not in {"active", "finished"}:
                        errors_list.append(f"Invalid status: {status}")
            if sc_no:
                sc_rows = conn.execute(
                    "SELECT sc_id FROM sc_records WHERE sc_no = ?", (sc_no,)
                ).fetchall()
                if len(sc_rows) == 0:
                    errors_list.append(f"SC with SC NO '{sc_no}' not found")
                elif len(sc_rows) > 1:
                    errors_list.append(f"SC NO '{sc_no}' matches {len(sc_rows)} records in DB (duplicate NO)")
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

        # File-level PO NO duplicate detection
        po_no_counts = {}
        for r in preview:
            po_no = (r.get("po_no") or "").strip()
            if po_no:
                po_no_counts[po_no] = po_no_counts.get(po_no, 0) + 1
        for r in preview:
            po_no = (r.get("po_no") or "").strip()
            if po_no and po_no_counts.get(po_no, 0) > 1:
                r["_errors"].append(f"PO NO '{po_no}' appears {po_no_counts[po_no]} times in this file")
                r["_valid"] = False

    return preview


def preview_gr_import(config: AppConfig, rows: list[dict]) -> list[dict]:
    """Validate GR rows without inserting. Returns rows annotated with _errors and _valid."""
    rows = _map_import_columns(rows, _GR_COLUMN_ALIASES)
    with connect(config) as conn:
        preview = []
        for row in rows:
            if _is_template_meta_row(row, "gr_no"):
                continue
            errors_list = []
            for field in ["po_no", "gr_no", "estimated_amount", "con_value", "delivery_from", "delivery_to", "status"]:
                val = row.get(field)
                if val is None or str(val).strip() == "":
                    errors_list.append(f"{field} is required")
            status = str(row.get("status", "")).strip()
            if status and status not in GR_IMPORT_ALLOWED_STATUSES:
                errors_list.append(f"Invalid status: {status}")
            # Resolve po_no → po_id
            po_no = str(row.get("po_no", "")).strip()
            if po_no:
                po_rows = conn.execute(
                    "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
                ).fetchall()
                if len(po_rows) == 0:
                    errors_list.append(f"PO with PO NO '{po_no}' not found")
                elif len(po_rows) > 1:
                    errors_list.append(f"PO NO '{po_no}' matches {len(po_rows)} records in DB (duplicate NO)")
            annotated = dict(row)
            annotated["_errors"] = errors_list
            annotated["_valid"] = len(errors_list) == 0
            preview.append(annotated)

        # File-level GR NO duplicate detection
        gr_no_counts = {}
        for r in preview:
            gr_no = (r.get("gr_no") or "").strip()
            if gr_no:
                gr_no_counts[gr_no] = gr_no_counts.get(gr_no, 0) + 1
        for r in preview:
            gr_no = (r.get("gr_no") or "").strip()
            if gr_no and gr_no_counts.get(gr_no, 0) > 1:
                r["_errors"].append(f"GR NO '{gr_no}' appears {gr_no_counts[gr_no]} times in this file")
                r["_valid"] = False

    return preview

def import_grs(config: AppConfig, current_user: dict, rows: list[dict]) -> dict:
    """Import GR records with direct status writes.

    ID fields are optional and auto-generated when empty.
    Duplicate IDs are silently skipped.
    Sample rows (ID = [EXAMPLE]) are silently skipped.
    """
    rows = _map_import_columns(rows, _GR_COLUMN_ALIASES)
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
                    if _is_template_meta_row(row, "gr_no"):
                        continue
                    gr_no = (row.get("gr_no") or "").strip()
                    exists = conn.execute(
                        "SELECT 1 FROM gr_requests WHERE gr_no = ?", (gr_no,)
                    ).fetchone()
                    if exists:
                        skipped_duplicate += 1
                        continue
                    # Resolve po_no → po_id
                    po_no = row.get("po_no", "").strip()
                    po_row = conn.execute(
                        "SELECT po_id FROM pos WHERE po_no = ?", (po_no,)
                    ).fetchone()
                    po_id = po_row["po_id"]
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
                            parse_date(row.get("delivery_from")),
                            parse_date(row.get("delivery_to")),
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
