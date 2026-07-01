"""Monthly summary: on the 1st of each month, send each requester a summary
of their active POs with remaining amounts and contract deadlines."""

import json
import logging
import sqlite3
from datetime import date, datetime, timezone

from sc_gr_app.notification import templates

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_last_summary_month(conn: sqlite3.Connection) -> str | None:
    """Return the last summary month string (YYYY-MM) from app_settings, or None."""
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.last_monthly_summary'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else None


def _set_last_summary_month(conn: sqlite3.Connection, year_month: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at)
           VALUES ('notify.last_monthly_summary', ?, ?)""",
        (json.dumps(year_month), _utc_now()),
    )


def resolve_emails(conn: sqlite3.Connection, user_ids: list[str]) -> dict[str, str]:
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT user_id, email FROM users WHERE user_id IN ({placeholders})",
        user_ids,
    ).fetchall()
    return {r["user_id"]: r["email"] for r in rows if r["email"]}


def check_monthly_summary(conn: sqlite3.Connection) -> int:
    """If today is the 1st of the month and we haven't sent the summary yet,
    queue a monthly summary for each requester with active POs.

    Returns the number of summary emails queued.
    """
    today = date.today()
    if today.day != 1:
        return 0

    year_month = today.strftime("%Y-%m")
    last = _get_last_summary_month(conn)
    if last == year_month:
        return 0  # Already sent this month

    # Find all active POs
    rows = conn.execute(
        """SELECT
               p.po_id, p.po_no, p.po_amount, p.contract_to, p.status,
               p.requester_id, u.user_name as requester_name, u.email as requester_email,
               sc.sc_no, v.vendor_name,
               p.po_amount - COALESCE(
                   (SELECT SUM(gr.con_value) FROM gr_requests gr
                    WHERE gr.po_id = p.po_id AND gr.status = 'approved'), 0
               ) as open_po_amount
           FROM pos p
           JOIN sc_records sc ON sc.sc_id = p.sc_id
           JOIN users u ON u.user_id = p.requester_id
           JOIN vendors v ON v.vendor_id = p.vendor_id
           WHERE p.status IN ('active', 'finished')
             AND p.contract_to IS NOT NULL
             AND p.po_amount IS NOT NULL
           ORDER BY p.requester_id, p.contract_to"""
    ).fetchall()

    if not rows:
        _set_last_summary_month(conn, year_month)
        return 0

    # Group POs by requester
    by_requester: dict[str, dict] = {}
    for row in rows:
        po = dict(row)
        rid = po["requester_id"]
        if rid not in by_requester:
            by_requester[rid] = {
                "requester_name": po["requester_name"],
                "requester_email": po.get("requester_email"),
                "pos": [],
            }

        # Compute remaining days
        remaining_days = None
        if po["contract_to"]:
            try:
                end_date = date.fromisoformat(po["contract_to"])
                remaining_days = (end_date - today).days
            except (ValueError, TypeError):
                pass

        po["remaining_days"] = remaining_days
        by_requester[rid]["pos"].append(po)

    # Queue summary entries
    timestamp = _utc_now()
    count = 0

    for rid, info in by_requester.items():
        body = templates.build_monthly_summary_body(
            requester_name=info["requester_name"],
            year=today.year,
            month=today.month,
            po_list=info["pos"],
        )
        subject = templates.build_monthly_summary_subject(today.year, today.month)

        # Store the HTML body directly in the queue entry
        # We use event_type = 'monthly_summary' and store the body+subject
        # in the entry as JSON in a special way
        conn.execute(
            """INSERT OR IGNORE INTO notification_queue
               (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
               VALUES (?, ?, 'monthly_summary', ?, ?, '[]', ?)""",
            (
                "po",
                rid,
                f"monthly:{year_month}",
                json.dumps([rid]),
                timestamp,
            ),
        )
        # Also store the rendered body/subject for later retrieval
        # Using the app_settings for the rendered content
        conn.execute(
            """INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at)
               VALUES (?, ?, ?)""",
            (
                f"notify.monthly_body.{rid}.{year_month}",
                json.dumps({"subject": subject, "body": body}),
                timestamp,
            ),
        )
        count += 1

    _set_last_summary_month(conn, year_month)
    return count
