"""Daily threshold check: scan active SCs for date/amount thresholds."""

import logging
import sqlite3
from datetime import datetime, timezone, date

from sc_gr_app.notification import queue as q
from sc_gr_app.notification import config as cfg

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_all_active_scs(conn: sqlite3.Connection) -> tuple[int, int]:
    """Check all approved SCs for threshold breaches. Returns (date_events, amount_events)."""
    rows = conn.execute(
        "SELECT * FROM sc_records WHERE status = 'approved' AND service_period_end IS NOT NULL AND sc_amount IS NOT NULL"
    ).fetchall()

    admin_recipients = cfg.get_admin_recipients(conn)
    today = date.today()
    timestamp = _utc_now()
    date_count = 0
    amount_count = 0

    for sc in rows:
        sc_dict = dict(sc)
        sc_id = sc_dict["sc_id"]
        entity_config = cfg.get_entity_config(conn, sc_id)

        if entity_config is not None and not entity_config["enabled"]:
            continue

        # Merge thresholds: per-SC overrides defaults
        date_thresholds = (
            entity_config["date_thresholds"]
            if entity_config and entity_config.get("date_thresholds")
            else cfg.get_default_date_thresholds(conn)
        )
        amount_thresholds = (
            entity_config["amount_thresholds"]
            if entity_config and entity_config.get("amount_thresholds")
            else cfg.get_default_amount_thresholds(conn)
        )

        cc_ids = entity_config["cc_user_ids"] if entity_config else []
        requester_id = sc_dict["requester_id"]

        to_ids = [requester_id] + admin_recipients
        to_ids = list(dict.fromkeys([uid for uid in to_ids if uid]))

        # Date check
        if sc_dict["service_period_end"]:
            try:
                end_date = date.fromisoformat(sc_dict["service_period_end"])
                remaining_days = (end_date - today).days

                for threshold_months in sorted(date_thresholds):
                    threshold_days = int(threshold_months * 30)
                    if remaining_days < threshold_days:
                        event_key = f"threshold_date:{threshold_months}m"
                        if not q.is_threshold_sent(conn, "sc", sc_id, event_key):
                            q.queue_threshold(conn, "sc", sc_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "sc", sc_id, event_key, timestamp)
                            date_count += 1
                            logger.info("Date threshold triggered: SC %s, %s (remaining: %s days)",
                                        sc_id, event_key, remaining_days)
                        break
            except (ValueError, TypeError):
                pass

        # Amount check
        sc_amount = sc_dict["sc_amount"]
        if sc_amount and sc_amount > 0:
            try:
                approved_gr_total_row = conn.execute(
                    """
                    SELECT COALESCE(SUM(gr.con_value), 0) as total
                    FROM gr_requests gr
                    JOIN pos ON gr.po_id = pos.po_id
                    WHERE pos.sc_id = ? AND gr.status = 'approved'
                    """,
                    (sc_id,),
                ).fetchone()
                spent = float(approved_gr_total_row["total"]) if approved_gr_total_row else 0.0
                remaining_pct = ((float(sc_amount) - spent) / float(sc_amount)) * 100

                for threshold_pct in sorted(amount_thresholds):
                    if remaining_pct < threshold_pct:
                        event_key = f"threshold_amount:{threshold_pct}%"
                        if not q.is_threshold_sent(conn, "sc", sc_id, event_key):
                            q.queue_threshold(conn, "sc", sc_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "sc", sc_id, event_key, timestamp)
                            amount_count += 1
                            logger.info("Amount threshold triggered: SC %s, %s (remaining: %.1f%%)",
                                        sc_id, event_key, remaining_pct)
                        break
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    return date_count, amount_count
