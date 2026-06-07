"""Read notification configuration, merging defaults with per-SC overrides."""

import json
import sqlite3


def get_admin_recipients(conn: sqlite3.Connection) -> list[str]:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.admin_recipients'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else []


def get_entity_config(conn: sqlite3.Connection, po_id: str) -> dict | None:
    row = conn.execute(
        "SELECT enabled, cc_user_ids, date_thresholds, amount_thresholds "
        "FROM notification_config WHERE entity_type = 'po' AND entity_id = ?",
        (po_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "enabled": bool(row["enabled"]),
        "cc_user_ids": json.loads(row["cc_user_ids"]),
        "date_thresholds": json.loads(row["date_thresholds"]),
        "amount_thresholds": json.loads(row["amount_thresholds"]),
    }


def get_default_date_thresholds(conn: sqlite3.Connection) -> list:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.default_date_thresholds'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]


def get_default_amount_thresholds(conn: sqlite3.Connection) -> list:
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = 'notify.default_amount_thresholds'"
    ).fetchone()
    return json.loads(row["setting_value"]) if row else [50, 30, 10]
