"""Poll loop orchestration for the notification script."""

import logging
import time
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.notification import sender, thresholds, monthly

logger = logging.getLogger(__name__)


def run_poll_loop(config: AppConfig, poll_interval: int = 300) -> None:
    """Run the notification poll loop indefinitely. Sends emails + periodic threshold checks.

    Args:
        config: AppConfig for DB access
        poll_interval: Seconds between pending queue checks (default 5 min)
    """
    last_threshold_check_date = None

    logger.info("Notification poll loop started. Poll interval: %ss", poll_interval)

    while True:
        try:
            with connect(config) as conn:
                # Process pending queue (every cycle)
                sent, failed = sender.process_pending(conn)
                if sent or failed:
                    logger.info("Pending queue: %s sent, %s failed", sent, failed)

                # Retry failed queue
                recovered, still_failed = sender.process_failed(conn)
                if recovered or still_failed:
                    logger.info("Failed retry: %s recovered, %s still failed", recovered, still_failed)

                # Daily checks (threshold + monthly summary)
                today = datetime.now(timezone.utc).date()
                if last_threshold_check_date != today:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        date_count, amount_count = thresholds.check_all_active_pos(conn)
                        conn.commit()
                        if date_count or amount_count:
                            logger.info("Daily threshold check: %s date events, %s amount events",
                                        date_count, amount_count)

                        # Monthly summary on the 1st
                        summary_count = monthly.check_monthly_summary(conn)
                        if summary_count:
                            conn.commit()
                            logger.info("Monthly summary: %s requester emails queued", summary_count)

                        last_threshold_check_date = today
                    except Exception:
                        conn.rollback()
                        raise

                conn.commit()

        except Exception:
            logger.exception("Error in poll cycle")

        time.sleep(poll_interval)


def run_once(config: AppConfig) -> None:
    """Run one cycle: process pending + failed + threshold check + monthly. For testing."""
    with connect(config) as conn:
        sent, failed = sender.process_pending(conn)
        logger.info("Pending: %s sent, %s failed", sent, failed)

        recovered, still_failed = sender.process_failed(conn)
        logger.info("Failed retry: %s recovered, %s still failed", recovered, still_failed)

        conn.execute("BEGIN IMMEDIATE")
        try:
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            logger.info("Thresholds: %s date, %s amount", date_count, amount_count)
        except Exception:
            conn.rollback()
            raise

        summary_count = monthly.check_monthly_summary(conn)
        if summary_count:
            logger.info("Monthly summary: %s requester emails queued", summary_count)

        conn.commit()


def run_thresholds_only(config: AppConfig) -> None:
    """Run only the threshold check. For scheduled daily run."""
    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            logger.info("Thresholds: %s date, %s amount", date_count, amount_count)
        except Exception:
            conn.rollback()
            raise
