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
