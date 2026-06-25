"""Daily threshold check: scan active POs for date/amount thresholds."""

import logging
import sqlite3
from datetime import datetime, timezone, date

from sc_gr_app.notification import queue as q
from sc_gr_app.notification import config as cfg

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_all_active_pos(conn: sqlite3.Connection) -> tuple[int, int]:
    """Check all active POs for threshold breaches. Returns (date_events, amount_events)."""
    rows = conn.execute(
        """SELECT po.*, sc.requester_id
           FROM pos po
           JOIN sc_records sc ON sc.sc_id = po.sc_id
           WHERE po.status IN ('activing', 'finished')
             AND po.contract_to IS NOT NULL
             AND po.po_amount IS NOT NULL"""
    ).fetchall()

    today = date.today()
    timestamp = _utc_now()
    date_count = 0
    amount_count = 0

    for row in rows:
        po = dict(row)
        po_id = po["po_id"]
        entity_config = cfg.get_entity_config(conn, po_id)

        if entity_config is not None and not entity_config["enabled"]:
            continue

        # Merge thresholds: per-PO overrides defaults
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
        requester_id = po["requester_id"]

        to_ids = [requester_id]
        to_ids = list(dict.fromkeys([uid for uid in to_ids if uid]))

        # Date check — use contract_to
        if po["contract_to"]:
            try:
                end_date = date.fromisoformat(po["contract_to"])
                remaining_days = (end_date - today).days

                for threshold_months in sorted(date_thresholds):
                    threshold_days = int(threshold_months * 30)
                    if remaining_days < threshold_days:
                        event_key = f"threshold_date:{threshold_months}m"
                        if not q.is_threshold_sent(conn, "po", po_id, event_key):
                            q.queue_threshold(conn, "po", po_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "po", po_id, event_key, timestamp)
                            date_count += 1
                            logger.info("Date threshold triggered: PO %s, %s (remaining: %s days)",
                                        po_id, event_key, remaining_days)
                        break
            except (ValueError, TypeError):
                pass

        # Amount check — use po_amount / open_po_amount
        po_amount = po["po_amount"]
        if po_amount and po_amount > 0:
            try:
                approved_gr_total_row = conn.execute(
                    """SELECT COALESCE(SUM(gr.con_value), 0) as total
                       FROM gr_requests gr
                       WHERE gr.po_id = ? AND gr.status = 'approved'""",
                    (po_id,),
                ).fetchone()
                spent = float(approved_gr_total_row["total"]) if approved_gr_total_row else 0.0
                remaining_pct = ((float(po_amount) - spent) / float(po_amount)) * 100

                for threshold_pct in sorted(amount_thresholds):
                    if remaining_pct < threshold_pct:
                        event_key = f"threshold_amount:{threshold_pct}%"
                        if not q.is_threshold_sent(conn, "po", po_id, event_key):
                            q.queue_threshold(conn, "po", po_id, event_key, to_ids, cc_ids, timestamp)
                            q.mark_threshold_sent(conn, "po", po_id, event_key, timestamp)
                            amount_count += 1
                            logger.info("Amount threshold triggered: PO %s, %s (remaining: %.1f%%)",
                                        po_id, event_key, remaining_pct)
                        break
            except (ValueError, TypeError, ZeroDivisionError):
                pass

    return date_count, amount_count
