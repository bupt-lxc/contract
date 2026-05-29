"""Read/write notification_queue. Shared pattern with desktop notification_service."""

import json
import sqlite3


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


def mark_failed(conn: sqlite3.Connection, queue_id: int, error_msg: str) -> None:
    conn.execute(
        "UPDATE notification_queue SET status = 'failed', error_msg = ? WHERE id = ?",
        (error_msg, queue_id),
    )


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
