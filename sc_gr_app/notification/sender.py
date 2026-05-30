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
            "SELECT * FROM pos WHERE po_id = ?", (entity_id,)
        ).fetchone()
    elif entity_type == "gr":
        row = conn.execute(
            "SELECT * FROM gr_requests WHERE gr_id = ?", (entity_id,)
        ).fetchone()
    else:
        row = None

    if row:
        entity_info = dict(row)

    subject = templates.build_subject(entry, entity_info)
    body = templates.build_body(entry, entity_info, {**to_emails_map, **cc_emails_map})

    # Look up attachments for this entity
    attachment_rows = conn.execute(
        "SELECT filename, stored_path FROM attachments WHERE entity_type = ? AND entity_id = ?",
        (entity_type, entity_id),
    ).fetchall()

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
    sent = 0
    failed = 0
    timestamp = _utc_now()

    for entry in entries:
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, entry["id"], timestamp)
                sent += 1
            else:
                queue.mark_failed(conn, entry["id"], "No valid To addresses")
                failed += 1
        except Exception as exc:
            queue.mark_failed(conn, entry["id"], str(exc))
            failed += 1
            logger.error("Failed to send queue entry %s: %s", entry["id"], exc)

    return sent, failed


def process_failed(conn: sqlite3.Connection) -> tuple[int, int]:
    """Retry all failed queue entries. Returns (recovered_count, still_failed_count)."""
    entries = queue.fetch_failed(conn)
    recovered = 0
    still_failed = 0
    timestamp = _utc_now()

    for entry in entries:
        try:
            if send_entry(conn, entry):
                queue.mark_sent(conn, entry["id"], timestamp)
                recovered += 1
            else:
                queue.mark_failed(conn, entry["id"], "No valid To addresses")
                still_failed += 1
        except Exception as exc:
            queue.mark_failed(conn, entry["id"], str(exc))
            still_failed += 1
            logger.error("Retry failed for queue entry %s: %s", entry["id"], exc)

    return recovered, still_failed
