"""Poll loop orchestration for the notification script."""

import logging
import time
from datetime import datetime, timezone

from sc_gr_app.config import AppConfig
from sc_gr_app.db.connection import connect
from sc_gr_app.notification import sender, thresholds, monthly, schedules

logger = logging.getLogger(__name__)


def run_poll_loop(config: AppConfig, poll_interval: int = 10) -> None:
    """Run the notification poll loop indefinitely. Sends emails + periodic threshold checks.

    Args:
        config: AppConfig for DB access
        poll_interval: Seconds between pending queue checks (default 10s)
    """
    last_threshold_check_date = None

    logger.info("Notification poll loop started. Poll interval: %ss", poll_interval)

    while True:
        try:
            with connect(config) as conn:
                sent, failed = sender.process_pending(conn)
                if sent:
                    logger.info("Sent: %d email(s) successfully", sent)
                if failed:
                    logger.warning("Failed: %d email(s)", failed)

                recovered, still_failed = sender.process_failed(conn)
                if recovered:
                    logger.info("Recovered: %d previously failed email(s) re-sent", recovered)
                if still_failed:
                    logger.warning("Still failed: %d email(s) after retry", still_failed)

            # Daily checks on a separate connection so explicit BEGIN IMMEDIATE
            # never collides with prior DML on the same handle.
            today = datetime.now(timezone.utc).date()
            if last_threshold_check_date != today:
                with connect(config) as conn:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        date_count, amount_count = thresholds.check_all_active_pos(conn)
                        if date_count or amount_count:
                            logger.info(
                                "Daily threshold check: %s date events, %s amount events",
                                date_count, amount_count)

                        schedule_count = schedules.check_custom_schedules(conn)
                        if schedule_count:
                            logger.info("Custom schedule check: %s events queued", schedule_count)

                        summary_count = monthly.check_monthly_summary(conn)
                        if summary_count:
                            logger.info("Monthly summary: %s requester emails queued", summary_count)

                        conn.commit()
                        last_threshold_check_date = today
                    except Exception:
                        conn.rollback()
                        raise

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

    with connect(config) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            logger.info("Thresholds: %s date, %s amount", date_count, amount_count)

            schedule_count = schedules.check_custom_schedules(conn)
            if schedule_count:
                logger.info("Custom schedule check: %s events queued", schedule_count)

            summary_count = monthly.check_monthly_summary(conn)
            if summary_count:
                logger.info("Monthly summary: %s requester emails queued", summary_count)

            conn.commit()
        except Exception:
            conn.rollback()
            raise


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
