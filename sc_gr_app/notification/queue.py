"""Read/write notification_queue. Shared pattern with desktop notification_service."""

import json
import logging
import sqlite3

logger = logging.getLogger(__name__)


def fetch_pending(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notification_queue WHERE status = 'pending' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def fetch_failed(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM notification_queue WHERE status = 'failed' ORDER BY created_at ASC"
    ).fetchall()
    return [dict(r) for r in rows]


def mark_sent(conn: sqlite3.Connection, queue_id: int, timestamp: str) -> None:
    conn.execute(
        "UPDATE notification_queue SET status = 'sent', sent_at = ? WHERE id = ?",
        (timestamp, queue_id),
    )
    logger.debug("Status change: queue #%d → sent", queue_id)


def mark_failed(conn: sqlite3.Connection, queue_id: int, error_msg: str) -> None:
    conn.execute(
        "UPDATE notification_queue SET status = 'failed', error_msg = ? WHERE id = ?",
        (error_msg, queue_id),
    )
    logger.debug("Status change: queue #%d → failed (%s)", queue_id, error_msg)


def queue_threshold(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_key: str,
    to_ids: list[str],
    cc_ids: list[str],
    timestamp: str,
) -> None:
    event_type = "threshold_date" if "date" in event_key else "threshold_amount"
    conn.execute(
        """
        INSERT OR IGNORE INTO notification_queue
            (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (entity_type, entity_id, event_type, event_key, json.dumps(to_ids), json.dumps(cc_ids), timestamp),
    )
    logger.debug("Queued threshold: %s/%s event=%s", entity_type, entity_id, event_key)


def is_threshold_sent(conn: sqlite3.Connection, entity_type: str, entity_id: str, event_key: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM notification_sent_threshold WHERE entity_type = ? AND entity_id = ? AND event_key = ?",
        (entity_type, entity_id, event_key),
    ).fetchone()
    return row is not None


def mark_threshold_sent(conn: sqlite3.Connection, entity_type: str, entity_id: str, event_key: str, timestamp: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO notification_sent_threshold (entity_type, entity_id, event_key, sent_at) VALUES (?, ?, ?, ?)",
        (entity_type, entity_id, event_key, timestamp),
    )
    logger.debug("Threshold marked sent: %s/%s event=%s", entity_type, entity_id, event_key)


def queue_custom_schedule(
    conn: sqlite3.Connection,
    entity_type: str,
    entity_id: str,
    event_key: str,
    to_ids: list[str],
    cc_ids: list[str],
    timestamp: str,
) -> None:
    """Insert a custom_schedule notification queue entry (idempotent)."""
    conn.execute(
        """
        INSERT OR IGNORE INTO notification_queue
            (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
        VALUES (?, ?, 'custom_schedule', ?, ?, ?, ?)
        """,
        (entity_type, entity_id, event_key, json.dumps(to_ids), json.dumps(cc_ids), timestamp),
    )
    logger.debug("Queued custom schedule: %s/%s event=%s", entity_type, entity_id, event_key)
