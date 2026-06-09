import json
import time

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.errors import AppError


def _utc_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


class QueueWriteError(AppError):
    code = "QUEUE_WRITE_ERROR"


def _read_app_setting(conn, key):
    row = conn.execute(
        "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
    ).fetchone()
    return json.loads(row["setting_value"]) if row else None


def _resolve_keyword(keyword, entity, current_user):
    """Resolve a single recipient keyword to a list of user IDs."""
    if keyword == "requester":
        requester_id = entity.get("requester_id")
        return [requester_id] if requester_id else []
    if keyword == "actor":
        return [current_user["user_id"]]
    if keyword == "notify.admin_recipients":
        return []
    return [keyword]


def resolve_recipients(conn, rule_to_or_cc, entity, current_user):
    """Resolve a to/cc rule array to a list of user IDs.

    Keywords: 'requester', 'actor', 'notify.admin_recipients', or direct user IDs.
    'notify.admin_recipients' is looked up from app_settings at resolve time.
    """
    result = []
    for item in rule_to_or_cc:
        if item == "notify.admin_recipients":
            admin_setting = _read_app_setting(conn, "notify.admin_recipients")
            if admin_setting:
                result.extend(admin_setting)
        else:
            resolved = _resolve_keyword(item, entity, current_user)
            result.extend(resolved)
    seen = set()
    unique = []
    for uid in result:
        if uid and uid not in seen:
            seen.add(uid)
            unique.append(uid)
    return unique


def queue_status_change(conn, entity_type, entity_id, transition, entity, current_user):
    """Insert a notification queue entry into the current transaction.

    Args:
        conn: Active sqlite3 connection (inside BEGIN IMMEDIATE)
        entity_type: 'sc' / 'po' / 'gr'
        entity_id: The entity's ID
        transition: 'submit' / 'approve' / 'deny' / 'close' / 'create' / 'finish' / 'cancel'
        entity: The entity dict (sc_record / po / gr) — used for requester_id
        current_user: The user dict performing the action — used for actor
    """
    transitions_key = f"notify.transitions.{entity_type}"
    rules_json = _read_app_setting(conn, transitions_key)
    if not rules_json:
        return

    rules = rules_json.get(transition)
    if not rules:
        return

    to_rule = rules.get("to", [])
    cc_rule = rules.get("cc", [])

    to_ids = resolve_recipients(conn, to_rule, entity, current_user)
    cc_ids = resolve_recipients(conn, cc_rule, entity, current_user)

    # Merge per-entity CC list
    entity_config_row = None
    if entity_type == "sc":
        entity_config_row = conn.execute(
            "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'sc' AND entity_id = ? AND enabled = 1",
            (entity_id,),
        ).fetchone()
    elif entity_type == "po":
        entity_config_row = conn.execute(
            "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'po' AND entity_id = ? AND enabled = 1",
            (entity_id,),
        ).fetchone()
    elif entity_type == "gr":
        gr_row = conn.execute(
            "SELECT po_id FROM gr_requests WHERE gr_id = ?", (entity_id,)
        ).fetchone()
        if gr_row:
            entity_config_row = conn.execute(
                "SELECT cc_user_ids FROM notification_config WHERE entity_type = 'po' AND entity_id = ? AND enabled = 1",
                (gr_row["po_id"],),
            ).fetchone()

    if entity_config_row:
        extra_cc = json.loads(entity_config_row["cc_user_ids"])
        for uid in extra_cc:
            if uid and uid not in cc_ids:
                cc_ids.append(uid)

    # Merge default CC list
    default_cc = _read_app_setting(conn, "notify.default_cc")
    if default_cc:
        for uid in default_cc:
            if uid and uid not in cc_ids:
                cc_ids.append(uid)

    # Remove primary recipients from CC
    cc_ids = [uid for uid in cc_ids if uid not in to_ids]

    if not to_ids:
        return

    timestamp = _utc_now()
    # If a pending entry already exists for the same event, refresh its
    # timestamp and recipients rather than silently dropping the duplicate.
    # This is important when an entity is revoked and re-submitted before
    # the notification script processes the first submit.
    existing = conn.execute(
        """SELECT id FROM notification_queue
           WHERE entity_type = ? AND entity_id = ? AND event_key = ? AND status = 'pending'""",
        (entity_type, entity_id, transition),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE notification_queue
               SET to_recipients = ?, cc_recipients = ?, created_at = ?
               WHERE id = ?""",
            (json.dumps(to_ids), json.dumps(cc_ids), timestamp, existing["id"]),
        )
    else:
        conn.execute(
            """
            INSERT INTO notification_queue
                (entity_type, entity_id, event_type, event_key, to_recipients, cc_recipients, created_at)
            VALUES (?, ?, 'status_change', ?, ?, ?, ?)
            """,
            (entity_type, entity_id, transition, json.dumps(to_ids), json.dumps(cc_ids), timestamp),
        )


def get_sc_notification_config(config: AppConfig, sc_id: str) -> dict | None:
    with connect(config) as conn:
        row = conn.execute(
            "SELECT enabled, cc_user_ids, date_thresholds, amount_thresholds "
            "FROM notification_config WHERE entity_type = 'sc' AND entity_id = ?",
            (sc_id,),
        ).fetchone()
        if row is not None:
            return {
                "enabled": bool(row["enabled"]),
                "cc_user_ids": json.loads(row["cc_user_ids"]),
                "date_thresholds": json.loads(row["date_thresholds"]),
                "amount_thresholds": json.loads(row["amount_thresholds"]),
            }

        default_cc = _read_app_setting(conn, "notify.default_cc") or []
        default_date = _read_app_setting(conn, "notify.default_date_thresholds") or [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        default_amount = _read_app_setting(conn, "notify.default_amount_thresholds") or [50, 30, 10]

        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids, date_thresholds, amount_thresholds)
                VALUES ('sc', ?, 1, ?, ?, ?)
                """,
                (
                    sc_id,
                    json.dumps(default_cc),
                    json.dumps(default_date),
                    json.dumps(default_amount),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "enabled": True,
            "cc_user_ids": default_cc,
            "date_thresholds": default_date,
            "amount_thresholds": default_amount,
        }


def save_sc_notification_config(config: AppConfig, sc_id: str, data: dict) -> None:
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids, date_thresholds, amount_thresholds)
                VALUES ('sc', ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    cc_user_ids = excluded.cc_user_ids,
                    date_thresholds = excluded.date_thresholds,
                    amount_thresholds = excluded.amount_thresholds
                """,
                (
                    sc_id,
                    1 if data.get("enabled", True) else 0,
                    json.dumps(data.get("cc_user_ids", [])),
                    json.dumps(data.get("date_thresholds", [])),
                    json.dumps(data.get("amount_thresholds", [])),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_po_notification_config(config: AppConfig, po_id: str) -> dict | None:
    with connect(config) as conn:
        row = conn.execute(
            "SELECT enabled, cc_user_ids, date_thresholds, amount_thresholds "
            "FROM notification_config WHERE entity_type = 'po' AND entity_id = ?",
            (po_id,),
        ).fetchone()
        if row is not None:
            return {
                "enabled": bool(row["enabled"]),
                "cc_user_ids": json.loads(row["cc_user_ids"]),
                "date_thresholds": json.loads(row["date_thresholds"]),
                "amount_thresholds": json.loads(row["amount_thresholds"]),
            }

        # No PO-specific config yet — snapshot current global defaults
        # into a dedicated row so future global changes don't affect this PO.
        default_cc = _read_app_setting(conn, "notify.default_cc") or []
        default_date = _read_app_setting(conn, "notify.default_date_thresholds") or [12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1]
        default_amount = _read_app_setting(conn, "notify.default_amount_thresholds") or [50, 30, 10]

        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids, date_thresholds, amount_thresholds)
                VALUES ('po', ?, 1, ?, ?, ?)
                """,
                (
                    po_id,
                    json.dumps(default_cc),
                    json.dumps(default_date),
                    json.dumps(default_amount),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise

        return {
            "enabled": True,
            "cc_user_ids": default_cc,
            "date_thresholds": default_date,
            "amount_thresholds": default_amount,
        }


def save_po_notification_config(config: AppConfig, po_id: str, data: dict) -> None:
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                """
                INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids, date_thresholds, amount_thresholds)
                VALUES ('po', ?, ?, ?, ?, ?)
                ON CONFLICT(entity_type, entity_id) DO UPDATE SET
                    enabled = excluded.enabled,
                    cc_user_ids = excluded.cc_user_ids,
                    date_thresholds = excluded.date_thresholds,
                    amount_thresholds = excluded.amount_thresholds
                """,
                (
                    po_id,
                    1 if data.get("enabled", True) else 0,
                    json.dumps(data.get("cc_user_ids", [])),
                    json.dumps(data.get("date_thresholds", [])),
                    json.dumps(data.get("amount_thresholds", [])),
                ),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def get_notification_defaults(config: AppConfig) -> dict:
    with connect(config) as conn:
        keys = [
            "notify.admin_recipients",
            "notify.transitions.sc",
            "notify.transitions.po",
            "notify.transitions.gr",
            "notify.default_cc",
            "notify.default_date_thresholds",
            "notify.default_amount_thresholds",
        ]
        result = {}
        for key in keys:
            row = conn.execute(
                "SELECT setting_value FROM app_settings WHERE setting_key = ?", (key,)
            ).fetchone()
            result[key] = json.loads(row["setting_value"]) if row else None
        return result


def save_notification_defaults(config: AppConfig, data: dict) -> None:
    field_map = {
        "admin_recipients": "notify.admin_recipients",
        "transitions": None,
        "default_cc": "notify.default_cc",
        "date_thresholds": "notify.default_date_thresholds",
        "amount_thresholds": "notify.default_amount_thresholds",
    }
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            timestamp = _utc_now()
            for data_key, setting_key in field_map.items():
                if setting_key and data_key in data:
                    conn.execute(
                        "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                        (setting_key, json.dumps(data[data_key]), timestamp),
                    )
            if "transitions" in data:
                transitions = data["transitions"]
                for entity_type in ("sc", "po", "gr"):
                    key = f"notify.transitions.{entity_type}"
                    if entity_type in transitions:
                        # Merge with existing to preserve transitions the UI
                        # may not know about (e.g. added by a later migration).
                        existing_row = conn.execute(
                            "SELECT setting_value FROM app_settings WHERE setting_key = ?",
                            (key,),
                        ).fetchone()
                        if existing_row:
                            existing = json.loads(existing_row["setting_value"])
                            # incoming takes precedence for keys it provides;
                            # existing keys not in incoming are preserved
                            merged = {**existing, **transitions[entity_type]}
                        else:
                            merged = transitions[entity_type]
                        conn.execute(
                            "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                            (key, json.dumps(merged), timestamp),
                        )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def list_notification_queue(
    config: AppConfig, sc_id: str | None = None, status: str | None = None,
    entity_type: str | None = None, entity_id: str | None = None,
    limit: int = 50, offset: int = 0,
) -> dict:
    with connect(config) as conn:
        conditions = []
        params = []
        if sc_id:
            conditions.append("entity_id = ?")
            params.append(sc_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if entity_type:
            conditions.append("entity_type = ?")
            params.append(entity_type)
        if entity_id:
            conditions.append("entity_id = ?")
            params.append(entity_id)
        where = "WHERE " + " AND ".join(conditions) if conditions else ""
        count_row = conn.execute(
            f"SELECT COUNT(*) as cnt FROM notification_queue {where}", params
        ).fetchone()
        rows = conn.execute(
            f"SELECT * FROM notification_queue {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return {
            "items": [dict(r) for r in rows],
            "total": count_row["cnt"],
        }


def get_po_custom_schedules(config: AppConfig, po_id: str) -> list[dict]:
    """Return all custom schedules for a PO."""
    with connect(config) as conn:
        rows = conn.execute(
            """SELECT * FROM notification_custom_schedule
               WHERE entity_type = 'po' AND entity_id = ? ORDER BY id""",
            (po_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def save_po_custom_schedules(config: AppConfig, po_id: str, schedules: list[dict]) -> None:
    """Replace all custom schedules for a PO with the given list."""
    timestamp = _utc_now()
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            conn.execute(
                "DELETE FROM notification_custom_schedule WHERE entity_type = 'po' AND entity_id = ?",
                (po_id,),
            )
            for s in schedules:
                _validate_schedule_data(s)
                conn.execute(
                    """INSERT INTO notification_custom_schedule
                       (entity_type, entity_id, schedule_type,
                        day_of_month, weekday, occurrence,
                        enabled, created_at, updated_at)
                       VALUES ('po', ?, ?, ?, ?, ?, 1, ?, ?)""",
                    (
                        po_id,
                        s["schedule_type"],
                        s.get("day_of_month"),
                        s.get("weekday"),
                        s.get("occurrence"),
                        timestamp,
                        timestamp,
                    ),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def _validate_schedule_data(s: dict) -> None:
    """Validate required fields per schedule_type. Raises ValidationError on invalid input."""
    from sc_gr_app.errors import ValidationError

    stype = s.get("schedule_type")
    if stype not in ("monthly_day", "monthly_weekday", "weekly_day"):
        raise ValidationError(f"Invalid schedule_type: {stype}")

    if stype == "monthly_day":
        day = s.get("day_of_month")
        if day is None or not isinstance(day, int) or day < 1 or day > 31:
            raise ValidationError("monthly_day requires day_of_month between 1 and 31")

    elif stype == "monthly_weekday":
        wd = s.get("weekday")
        if wd is None or not isinstance(wd, int) or wd < 0 or wd > 6:
            raise ValidationError("monthly_weekday requires weekday between 0 and 6")
        occ = s.get("occurrence")
        if occ not in ("first", "second", "third", "fourth", "last"):
            raise ValidationError("monthly_weekday requires occurrence: first/second/third/fourth/last")

    elif stype == "weekly_day":
        wd = s.get("weekday")
        if wd is None or not isinstance(wd, int) or wd < 0 or wd > 6:
            raise ValidationError("weekly_day requires weekday between 0 and 6")
