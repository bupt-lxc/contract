import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import ValidationError
from sc_gr_app.rbac import require_requester_or_admin
from sc_gr_app.services.record_service import write_operation_record
from sc_gr_app.services.lock_service import LeaseLock


REQUIRED_FIELDS = ("vendor_name", "service_scope")
SUPPORTED_SERVICE_SCOPES = {
    "Transportation",
    "engineering Service",
    "Equipment",
    "Parts",
    "Driver",
    "Test car rental",
    "General Service",
    "Dealers",
    "Import&Export&cusoms clearance",
    "Insurance",
    "Harness",
    "Maintenance",
    "Security",
    "Testing support",
    "Others",
}
OPTIONAL_FIELDS = (
    "ksrm_vendor_code",
    "company_name_cn",
    "contact_person",
    "phone",
    "email",
    "description",
    "inquiry_history",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _require_fields(data: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if data.get(field) in (None, ""):
            raise ValidationError(f"{field} is required")


def _row_to_dict(row) -> dict:
    return dict(row)


def _get_vendor(conn, vendor_id: str) -> dict:
    return _row_to_dict(
        conn.execute(
            "select * from vendors where vendor_id = ?",
            (vendor_id,),
        ).fetchone()
    )


def create_vendor(config: AppConfig, current_user: dict, data: dict) -> dict:
    require_requester_or_admin(current_user)
    _require_fields(data, REQUIRED_FIELDS)
    if data["service_scope"] not in SUPPORTED_SERVICE_SCOPES:
        raise ValidationError("service_scope is invalid")

    timestamp = utc_now()

    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                # Auto-generate vendor_id if not provided: V + 6-digit sequence
                vendor_id = data.get("vendor_id", "").strip()
                if not vendor_id:
                    vendor_id = _generate_vendor_id(conn)
                else:
                    # Verify vendor_id is not already taken
                    existing = conn.execute(
                        "SELECT 1 FROM vendors WHERE vendor_id = ?", (vendor_id,)
                    ).fetchone()
                    if existing:
                        raise ValidationError(f"vendor_id '{vendor_id}' already exists")

                conn.execute(
                    """
                    insert into vendors (
                      vendor_id,
                      vendor_name,
                      ksrm_vendor_code,
                      company_name_cn,
                      contact_person,
                      phone,
                      service_scope,
                      email,
                      description,
                      inquiry_history,
                      created_by,
                      created_at,
                      updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vendor_id,
                        data["vendor_name"],
                        data.get("ksrm_vendor_code"),
                        data.get("company_name_cn"),
                        data.get("contact_person"),
                        data.get("phone"),
                        data["service_scope"],
                        data.get("email"),
                        data.get("description"),
                        data.get("inquiry_history"),
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                    ),
                )
                created = _get_vendor(conn, vendor_id)
                write_operation_record(
                    conn,
                    action_type="create_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
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


def search_vendors(config: AppConfig, text: str | None = None) -> list[dict]:
    with connect(config) as conn:
        if text:
            like_text = f"%{text.lower()}%"
            rows = conn.execute(
                """
                select *
                from vendors
                where lower(vendor_name) like ?
                   or lower(coalesce(ksrm_vendor_code, '')) like ?
                order by vendor_name asc
                """,
                (like_text, like_text),
            ).fetchall()
        else:
            rows = conn.execute(
                "select * from vendors order by vendor_name asc"
            ).fetchall()

    return [_row_to_dict(row) for row in rows]


def update_vendor(config: AppConfig, current_user: dict, vendor_id: str, data: dict) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_vendor(conn, vendor_id)
                if not before:
                    raise ValidationError(f"Vendor {vendor_id} not found")

                timestamp = utc_now()
                fields = [
                    "vendor_name", "ksrm_vendor_code", "company_name_cn",
                    "contact_person", "phone", "service_scope", "email",
                    "description", "inquiry_history"
                ]
                if "service_scope" in data and data["service_scope"] not in SUPPORTED_SERVICE_SCOPES:
                    raise ValidationError("service_scope is invalid")

                for field in fields:
                    if field in data:
                        conn.execute(
                            f"update vendors set {field} = ?, updated_at = ? where vendor_id = ?",
                            (data[field], timestamp, vendor_id)
                        )

                after = _get_vendor(conn, vendor_id)
                write_operation_record(
                    conn,
                    action_type="update_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
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


def disable_vendor(config: AppConfig, current_user: dict, vendor_id: str) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_vendor(conn, vendor_id)
                if not before:
                    raise ValidationError(f"Vendor {vendor_id} not found")
                timestamp = utc_now()
                conn.execute(
                    "update vendors set status = 'disabled', updated_at = ? where vendor_id = ?",
                    (timestamp, vendor_id)
                )
                after = _get_vendor(conn, vendor_id)
                write_operation_record(
                    conn,
                    action_type="disable_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
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


def delete_vendor(config: AppConfig, current_user: dict, vendor_id: str) -> dict:
    require_requester_or_admin(current_user)
    with LeaseLock(config.lock_dir, "system", current_user["machine_id"]):
        with connect(config) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                before = _get_vendor(conn, vendor_id)
                if not before:
                    raise ValidationError(f"Vendor {vendor_id} not found")
                dep_count = conn.execute(
                    "select count(*) from pos where vendor_id = ?",
                    (vendor_id,),
                ).fetchone()[0]
                if dep_count > 0:
                    raise ValidationError(
                        f"Cannot delete vendor '{before['vendor_name']}': "
                        f"it is referenced by {dep_count} purchase order(s). "
                        f"Please delete the related POs first."
                    )
                conn.execute("delete from vendors where vendor_id = ?", (vendor_id,))
                write_operation_record(
                    conn,
                    action_type="delete_vendor",
                    object_type="vendor",
                    object_id=vendor_id,
                    sc_id=None,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=before,
                    after=None,
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise
    return {"deleted": vendor_id}


def check_ksrm_duplicate(config: AppConfig, ksrm_code: str, exclude_vendor_id: str | None = None) -> dict | None:
    """Return existing vendor dict if ksrm_vendor_code is already in use, else None."""
    if not ksrm_code or not ksrm_code.strip():
        return None
    with connect(config) as conn:
        if exclude_vendor_id:
            row = conn.execute(
                "select * from vendors where ksrm_vendor_code = ? and vendor_id != ?",
                (ksrm_code.strip(), exclude_vendor_id),
            ).fetchone()
        else:
            row = conn.execute(
                "select * from vendors where ksrm_vendor_code = ?",
                (ksrm_code.strip(),),
            ).fetchone()
        return _row_to_dict(row) if row else None


# ── Vendor import ──

VENDOR_COLUMN_MAP = {
    "vendor_id": "供应商ID",
    "vendor_name": "供应商名称",
    "ksrm_vendor_code": "KSRM代码",
    "company_name_cn": "公司中文名",
    "contact_person": "联系人",
    "phone": "电话",
    "service_scope": "服务范围",
    "email": "邮箱",
    "description": "描述",
    "inquiry_history": "询价历史",
}

VENDOR_IMPORT_FIELDS = list(VENDOR_COLUMN_MAP.keys())


def parse_vendor_file(file_path: str) -> list[dict]:
    """Parse an Excel (.xlsx/.xls) or CSV file and return a list of vendor dicts."""
    ext = Path(file_path).suffix.lower()

    if ext in (".xlsx", ".xls"):
        return _parse_excel(file_path)
    elif ext == ".csv":
        return _parse_csv(file_path)
    else:
        raise ValidationError(f"Unsupported file type: {ext}. Please use .xlsx, .xls, or .csv")


def _parse_excel(file_path: str) -> list[dict]:
    """Parse Excel file, using header row to map columns to vendor fields."""
    import openpyxl

    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(min_row=1, values_only=True)
    try:
        header = [str(c).strip() if c else "" for c in next(rows_iter)]
    except StopIteration:
        wb.close()
        raise ValidationError("File is empty")

    col_map = {}
    for idx, col_name in enumerate(header):
        col_lower = col_name.lower().replace(" ", "_")
        for field_key, cn_label in VENDOR_COLUMN_MAP.items():
            if col_lower == field_key.lower() or col_name.strip() == cn_label:
                col_map[idx] = field_key
                break

    if not col_map:
        wb.close()
        raise ValidationError(
            "No recognized columns found. Expected headers: "
            + ", ".join(VENDOR_COLUMN_MAP.keys())
        )

    rows = []
    for row in rows_iter:
        record = {}
        for idx, field_key in col_map.items():
            value = row[idx] if idx < len(row) else None
            record[field_key] = str(value).strip() if value is not None else ""
        rows.append(record)

    wb.close()
    return rows


def _parse_csv(file_path: str) -> list[dict]:
    """Parse CSV file, using header row to map columns to vendor fields."""
    with open(file_path, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        try:
            header = [c.strip() for c in next(reader)]
        except StopIteration:
            raise ValidationError("File is empty")

    col_map = {}
    for idx, col_name in enumerate(header):
        col_lower = col_name.lower().replace(" ", "_")
        for field_key, cn_label in VENDOR_COLUMN_MAP.items():
            if col_lower == field_key.lower() or col_name.strip() == cn_label:
                col_map[idx] = field_key
                break

    if not col_map:
        raise ValidationError(
            "No recognized columns found. Expected headers: "
            + ", ".join(VENDOR_COLUMN_MAP.keys())
        )

    rows = []
    for row in reader:
        record = {}
        for idx, field_key in col_map.items():
            value = row[idx] if idx < len(row) else ""
            record[field_key] = value.strip() if value else ""
        rows.append(record)

    return rows


def preview_import(config: AppConfig, file_path: str) -> list[dict]:
    """Parse file and return preview with validation errors for each row."""
    records = parse_vendor_file(file_path)
    if not records:
        raise ValidationError("No data rows found in file")

    with connect(config) as conn:
        existing_ids = set(
            r[0] for r in conn.execute("select vendor_id from vendors").fetchall()
        )
        existing_ksrm = set(
            r[0] for r in conn.execute(
                "select coalesce(ksrm_vendor_code, '') from vendors where ksrm_vendor_code is not null and ksrm_vendor_code != ''"
            ).fetchall()
        )

    preview = []
    for rec in records:
        errors_list = []
        warnings_list = []
        if not rec.get("vendor_name", "").strip():
            errors_list.append("vendor_name is required")
        if not rec.get("service_scope", "").strip():
            errors_list.append("service_scope is required")

        vid = rec.get("vendor_id", "").strip()
        if vid and vid in existing_ids:
            errors_list.append(f"vendor_id '{vid}' already exists")

        ksrm = rec.get("ksrm_vendor_code", "").strip()
        if ksrm and ksrm in existing_ksrm:
            warnings_list.append(f"KSRM code '{ksrm}' already exists in database")

        rec["_errors"] = errors_list
        rec["_warnings"] = warnings_list
        rec["_valid"] = len(errors_list) == 0
        preview.append(rec)

    return preview


def _generate_vendor_id(conn) -> str:
    """Generate a unique vendor_id as V + 6-digit sequence, picking up after max existing."""
    row = conn.execute(
        "SELECT COALESCE(MAX(CAST(SUBSTR(vendor_id, 2) AS INTEGER)), 0) + 1 AS next_id FROM vendors"
    ).fetchone()
    return f"V{int(row['next_id']):06d}"


def execute_import(
    config: AppConfig, current_user: dict, rows: list[dict]
) -> dict:
    """Import a list of validated vendor rows into the database."""
    require_requester_or_admin(current_user)

    timestamp = utc_now()
    imported = 0
    skipped = 0
    errors = []

    with connect(config) as conn:
        existing_ids = set(
            r[0] for r in conn.execute("select vendor_id from vendors").fetchall()
        )
        existing_ksrm = set(
            r[0] for r in conn.execute(
                "select coalesce(ksrm_vendor_code, '') from vendors where ksrm_vendor_code is not null and ksrm_vendor_code != ''"
            ).fetchall()
        )

        for i, rec in enumerate(rows):
            vid = rec.get("vendor_id", "").strip()
            if not vid:
                vid = _generate_vendor_id(conn)
            if vid in existing_ids:
                skipped += 1
                errors.append(f"Row {i + 1}: vendor_id '{vid}' already exists, skipped")
                continue

            ksrm = rec.get("ksrm_vendor_code", "").strip()
            if ksrm and ksrm in existing_ksrm:
                skipped += 1
                errors.append(f"Row {i + 1}: KSRM code '{ksrm}' already exists, skipped")
                continue

            vname = rec.get("vendor_name", "").strip()
            scope = rec.get("service_scope", "").strip()
            if not vname or not scope:
                skipped += 1
                errors.append(f"Row {i + 1}: missing required fields, skipped")
                continue

            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    """
                    insert into vendors (
                      vendor_id, vendor_name, ksrm_vendor_code, company_name_cn,
                      contact_person, phone, service_scope, email,
                      description, inquiry_history, created_by, created_at, updated_at
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        vid,
                        vname,
                        rec.get("ksrm_vendor_code", "").strip() or None,
                        rec.get("company_name_cn", "").strip() or None,
                        rec.get("contact_person", "").strip() or None,
                        rec.get("phone", "").strip() or None,
                        scope,
                        rec.get("email", "").strip() or None,
                        rec.get("description", "").strip() or None,
                        rec.get("inquiry_history", "").strip() or None,
                        current_user["user_id"],
                        timestamp,
                        timestamp,
                    ),
                )
                write_operation_record(
                    conn,
                    action_type="import_vendor",
                    object_type="vendor",
                    object_id=vid,
                    sc_id=None,
                    operator_id=current_user["user_id"],
                    machine_id=current_user["machine_id"],
                    before=None,
                    after={"vendor_id": vid, "vendor_name": vname, "service_scope": scope},
                )
                conn.commit()
                existing_ids.add(vid)
                if ksrm:
                    existing_ksrm.add(ksrm)
                imported += 1
            except Exception:
                conn.rollback()
                skipped += 1
                errors.append(f"Row {i + 1} ({vid}): insert failed, skipped")

    return {"imported": imported, "skipped": skipped, "errors": errors}
