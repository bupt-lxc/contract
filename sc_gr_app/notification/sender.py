"""Send email via Outlook COM (win32com)."""

import json
import logging
import sqlite3
from datetime import datetime, timezone

from sc_gr_app.notification import queue, templates

logger = logging.getLogger(__name__)

_draft_mode = False


def set_draft_mode(enabled: bool) -> None:
    """Enable draft mode: emails are saved to Drafts folder instead of being sent."""
    global _draft_mode
    _draft_mode = enabled
    if enabled:
        logger.info("Draft mode enabled — emails will be saved to Drafts folder")


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get_monthly_content(conn, entry) -> tuple[str, str]:
    """Retrieve pre-rendered monthly summary body and subject from app_settings."""
    rid = entry["entity_id"]
    year_month = entry["event_key"].replace("monthly:", "")
    key = f"notify.monthly_body.{rid}.{year_month}"
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    if row:
        data = json.loads(row["setting_value"])
        return data.get("body", ""), data.get("subject", "")
    return "", "[Contract] Monthly PO Summary"


def _attach_budget_info(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    entity_info: dict,
) -> None:
    """Compute and attach current open/consumed amounts to entity_info in-place.

    Queries GR totals at send time so the email reflects real-time budget state.
    """
    if entity_type == "po":
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN status = 'approved'
                                 THEN con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN COALESCE(gross_cost, estimated_amount)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests
            WHERE po_id = ?
            """,
            (entity_id,),
        ).fetchone()
        po_amount = entity_info.get("po_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        entity_info["open_po_amount"] = po_amount - pending - approved
        entity_info["consumed_amount"] = approved
        entity_info["pending_total"] = pending
        entity_info["pending_total_incl_tax"] = pending_incl_tax

    elif entity_type == "sc":
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN gr.status IN ('pending', 'manager_confirm')
                                 THEN COALESCE(gr.con_value, gr.estimated_amount) ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN gr.status = 'approved'
                                 THEN gr.con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN gr.status IN ('pending', 'manager_confirm')
                                 THEN COALESCE(gr.gross_cost, gr.estimated_amount)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests gr
            JOIN pos po ON po.po_id = gr.po_id
            WHERE po.sc_id = ?
            """,
            (entity_id,),
        ).fetchone()
        sc_amount = entity_info.get("sc_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        entity_info["sc_available_amount"] = sc_amount - pending - approved
        entity_info["consumed_amount"] = approved
        entity_info["pending_total"] = pending
        entity_info["pending_total_incl_tax"] = pending_incl_tax

        # Also attach all child POs with their budget info
        _attach_child_pos(conn, entity_id, entity_info)

        # Attach vendor list for the email body
        _attach_sc_vendors(conn, entity_id, entity_info)

    elif entity_type == "po":
        # Also attach all child GRs under this PO
        _attach_child_grs(conn, entity_id, entity_info)


def _attach_child_pos(
    conn: sqlite3.Connection,
    sc_id: str,
    entity_info: dict,
) -> None:
    """Query all POs under an SC with their budget info, attach as child_pos list."""
    rows = conn.execute(
        """
        SELECT p.po_id, p.po_no, p.po_amount, p.status, p.contract_to,
               v.vendor_name
        FROM pos p
        LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
        WHERE p.sc_id = ?
        ORDER BY p.po_no
        """,
        (sc_id,),
    ).fetchall()

    child_pos = []
    for r in rows:
        po = dict(r)
        # Compute per-PO open amount
        gr_totals = conn.execute(
            """
            SELECT
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN estimated_amount ELSE 0 END), 0) AS pending_total,
              COALESCE(SUM(CASE WHEN status = 'approved'
                                 THEN con_value ELSE 0 END), 0) AS con_value_total,
              COALESCE(SUM(CASE WHEN status IN ('pending', 'manager_confirm')
                                 THEN COALESCE(gross_cost, estimated_amount)
                                 ELSE 0 END), 0) AS pending_total_incl_tax
            FROM gr_requests
            WHERE po_id = ?
            """,
            (po["po_id"],),
        ).fetchone()
        po_amount = po.get("po_amount") or 0
        pending = gr_totals["pending_total"] or 0
        approved = gr_totals["con_value_total"] or 0
        pending_incl_tax = gr_totals["pending_total_incl_tax"] or 0
        po["open_po_amount"] = po_amount - pending - approved
        po["consumed_amount"] = approved
        po["pending_total"] = pending
        po["pending_total_incl_tax"] = pending_incl_tax
        child_pos.append(po)

    entity_info["child_pos"] = child_pos


def _attach_child_grs(
    conn: sqlite3.Connection,
    po_id: str,
    entity_info: dict,
) -> None:
    """Query all GRs under a PO, attach as child_grs list."""
    rows = conn.execute(
        """
        SELECT gr_id, gr_no, estimated_amount, con_value, gross_cost, status,
               goods_service_description, delivery_from, delivery_to
        FROM gr_requests
        WHERE po_id = ?
        ORDER BY gr_no
        """,
        (po_id,),
    ).fetchall()

    child_grs = []
    for r in rows:
        gr = dict(r)
        child_grs.append(gr)

    entity_info["child_grs"] = child_grs


def _attach_sc_vendors(
    conn: sqlite3.Connection,
    sc_id: str,
    entity_info: dict,
) -> None:
    """Query all vendors linked to an SC, attach as _vendors list for the email body."""
    rows = conn.execute(
        """
        SELECT v.vendor_id, v.vendor_name, v.service_scope,
               v.contact_person, v.phone, v.email
        FROM sc_vendors scv
        JOIN vendors v ON v.vendor_id = scv.vendor_id
        WHERE scv.sc_id = ?
        ORDER BY v.vendor_name
        """,
        (sc_id,),
    ).fetchall()
    entity_info["_vendors"] = [dict(r) for r in rows]



def resolve_emails(conn: sqlite3.Connection, user_ids: list[str]) -> dict[str, str]:
    """Map user IDs to email addresses from the users table."""
    if not user_ids:
        return {}
    placeholders = ",".join("?" * len(user_ids))
    rows = conn.execute(
        f"SELECT user_id, email FROM users WHERE user_id IN ({placeholders})",
        user_ids,
    ).fetchall()
    return {r["user_id"]: r["email"] for r in rows if r["email"]}


def resolve_user_name(conn: sqlite3.Connection, user_id: str) -> str:
    """Look up a user's display name. Returns the user_name or user_id if not found."""
    if not user_id:
        return ""
    row = conn.execute(
        "SELECT user_name FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["user_name"] if row else user_id


def generate_draft(conn: sqlite3.Connection, entry: dict) -> dict:
    """Generate email content for preview without sending.

    Returns {subject, html_body, to_addresses, cc_addresses, attachments, attachment_paths}.
    """
    to_ids = json.loads(entry["to_recipients"])
    cc_ids = json.loads(entry["cc_recipients"])
    to_emails_map = resolve_emails(conn, to_ids)
    cc_emails_map = resolve_emails(conn, cc_ids)
    to_addresses = [to_emails_map[uid] for uid in to_ids if uid in to_emails_map]
    cc_addresses = [cc_emails_map[uid] for uid in cc_ids if uid in cc_emails_map]

    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    entity_info = {}
    if entity_type == "sc":
        row = conn.execute("SELECT * FROM sc_records WHERE sc_id = ?", (entity_id,)).fetchone()
    elif entity_type == "po":
        row = conn.execute(
            """SELECT p.*, v.vendor_name FROM pos p
               LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
               WHERE p.po_id = ?""", (entity_id,)
        ).fetchone()
    elif entity_type == "gr":
        row = conn.execute("SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)).fetchone()
    else:
        row = None
    if row:
        entity_info = dict(row)

    _attach_budget_info(conn, entity_type, entity_id, entity_info)

    actor_id = entry.get("actor_id") or ""
    actor_name = resolve_user_name(conn, actor_id) if actor_id else ""
    requester_id = entity_info.get("requester_id") or ""
    requester_name = resolve_user_name(conn, requester_id) if requester_id else ""

    # Look up attachments
    attachment_rows = conn.execute(
        "SELECT filename, stored_path FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()
    entity_info["_attachments"] = [r["filename"] for r in attachment_rows]
    attachment_paths = [r["stored_path"] for r in attachment_rows]

    subject = templates.build_subject(entry, entity_info, actor_name=actor_name)
    # Append daily sequence
    today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq = conn.execute(
        "SELECT COUNT(*) FROM notification_queue WHERE date(created_at) = date('now')"
    ).fetchone()[0]
    subject = f"{subject}-{seq:03d}"
    body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map},
                                actor_name=actor_name, requester_name=requester_name)

    return {
        "subject": subject,
        "html_body": body,
        "to_addresses": to_addresses,
        "cc_addresses": cc_addresses,
        "attachments": [r["filename"] for r in attachment_rows],
        "attachment_paths": attachment_paths,
    }


def send_entry(conn: sqlite3.Connection, entry: dict) -> bool:
    """Send a single queue entry via Outlook. Returns True on success."""
    import pythoncom
    import win32com.client

    to_ids = json.loads(entry["to_recipients"])
    cc_ids = json.loads(entry["cc_recipients"])

    to_emails_map = resolve_emails(conn, to_ids)
    cc_emails_map = resolve_emails(conn, cc_ids)

    to_addresses = [to_emails_map[uid] for uid in to_ids if uid in to_emails_map]
    cc_addresses = [cc_emails_map[uid] for uid in cc_ids if uid in cc_emails_map]

    if not to_addresses:
        logger.warning("No valid To addresses for queue entry %s, skipping", entry["id"])
        return False

    # Get entity info for the email body
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    entity_info = {}
    if entity_type == "sc":
        row = conn.execute(
            "SELECT * FROM sc_records WHERE sc_id = ?", (entity_id,)
        ).fetchone()
    elif entity_type == "po":
        row = conn.execute(
            """SELECT p.*, v.vendor_name
               FROM pos p
               LEFT JOIN vendors v ON v.vendor_id = p.vendor_id
               WHERE p.po_id = ?""", (entity_id,)
        ).fetchone()
    elif entity_type == "gr":
        row = conn.execute(
            "SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)
        ).fetchone()
    else:
        row = None

    if row:
        entity_info = dict(row)

    # Compute current budget (open amount) at send time for PO and SC emails
    _attach_budget_info(conn, entity_type, entity_id, entity_info)

    # Resolve actor and requester names for the email body
    actor_id = entry.get("actor_id") or ""
    actor_name = resolve_user_name(conn, actor_id) if actor_id else ""
    requester_id = entity_info.get("requester_id") or ""
    requester_name = resolve_user_name(conn, requester_id) if requester_id else ""

    # Look up attachments — used for both display names and Outlook attachment files
    attachment_rows = conn.execute(
        "SELECT filename, stored_path FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()
    entity_info["_attachments"] = [r["filename"] for r in attachment_rows]

    # Monthly summary: body and subject are pre-rendered and stored in app_settings
    if entry["event_type"] == "monthly_summary":
        body, subject = _get_monthly_content(conn, entry)
    else:
        subject = templates.build_subject(entry, entity_info, actor_name=actor_name)
        # Append daily sequence number
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        seq = conn.execute(
            "SELECT COUNT(*) FROM notification_queue WHERE date(created_at) = date('now')"
        ).fetchone()[0]
        subject = f"{subject}-{seq:03d}"
        body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map},
                                    actor_name=actor_name, requester_name=requester_name)

    pythoncom.CoInitialize()
    try:
        outlook = win32com.client.Dispatch("Outlook.Application")
        mail = outlook.CreateItem(0)  # 0 = olMailItem
        mail.Subject = subject
        mail.HTMLBody = body
        mail.To = "; ".join(to_addresses)
        if cc_addresses:
            mail.CC = "; ".join(cc_addresses)
        for att in attachment_rows:
            try:
                mail.Attachments.Add(att["stored_path"])
            except Exception:
                logger.warning(
                    "Failed to attach %s for queue entry %s", att["filename"], entry["id"]
                )
        if _draft_mode:
            mail.Save()
            logger.info("Saved queue entry %s to Drafts: %s", entry["id"], subject)
        else:
            mail.Send()
            logger.info("Sent queue entry %s: %s", entry["id"], subject)
        return True
    finally:
        pythoncom.CoUninitialize()


def process_pending(conn: sqlite3.Connection) -> tuple[int, int]:
    """Send all pending queue entries. Returns (sent_count, failed_count)."""
    entries = queue.fetch_pending(conn)
    if not entries:
        return 0, 0

    logger.debug("Processing %d pending queue entries", len(entries))
    sent = 0
    failed = 0
    timestamp = _utc_now()

    for entry in entries:
        eid = entry["id"]
        entity_type = entry["entity_type"]
        entity_id = entry["entity_id"]
        event_type = entry["event_type"]
        logger.debug(
            "Sending queue #%d: type=%s entity=%s/%s event=%s",
            eid, entity_type, entity_id, event_type, entry["event_key"],
        )
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, eid, timestamp)
                sent += 1
                logger.info(
                    "SENT queue #%d: %s/%s (%s)", eid, entity_type, entity_id, event_type,
                )
            else:
                queue.mark_failed(conn, eid, "No valid To addresses")
                failed += 1
                logger.warning(
                    "FAILED queue #%d: %s/%s — no valid To addresses",
                    eid, entity_type, entity_id,
                )
        except Exception as exc:
            queue.mark_failed(conn, eid, str(exc))
            failed += 1
            logger.error(
                "ERROR queue #%d: %s/%s — %s", eid, entity_type, entity_id, exc,
            )

    return sent, failed


def process_failed(conn: sqlite3.Connection) -> tuple[int, int]:
    """Retry all failed queue entries. Returns (recovered_count, still_failed_count)."""
    entries = queue.fetch_failed(conn)
    if not entries:
        return 0, 0

    logger.debug("Retrying %d failed queue entries", len(entries))
    recovered = 0
    still_failed = 0
    timestamp = _utc_now()

    for entry in entries:
        eid = entry["id"]
        entity_type = entry["entity_type"]
        entity_id = entry["entity_id"]
        logger.debug(
            "Retrying queue #%d: type=%s entity=%s/%s",
            eid, entity_type, entity_id, entry["event_type"],
        )
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, eid, timestamp)
                recovered += 1
                logger.info(
                    "RECOVERED queue #%d: %s/%s (retry succeeded)",
                    eid, entity_type, entity_id,
                )
            else:
                queue.mark_failed(conn, eid, "No valid To addresses")
                still_failed += 1
                logger.warning(
                    "STILL FAILED queue #%d: %s/%s — no valid To addresses",
                    eid, entity_type, entity_id,
                )
        except Exception as exc:
            queue.mark_failed(conn, eid, str(exc))
            still_failed += 1
            logger.error(
                "RETRY ERROR queue #%d: %s/%s — %s", eid, entity_type, entity_id, exc,
            )

    return recovered, still_failed
