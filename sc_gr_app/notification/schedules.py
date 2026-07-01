"""Daily custom schedule check: fire notifications for POs whose custom
schedules match today's date.

Unlike threshold events which fire once when a remaining-months or
remaining-percentage boundary is crossed, custom schedules fire every
time their calendar-based condition is met (e.g., every 15th of the month,
every first Monday, every Wednesday).
"""

import calendar
import logging
import sqlite3
from datetime import date, datetime, timezone

from sc_gr_app.notification import queue as q
from sc_gr_app.notification import config as cfg

logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def check_custom_schedules(conn: sqlite3.Connection) -> int:
    """Check all active POs for custom schedule matches against today.
    Returns number of events queued.
    """
    today = date.today()
    timestamp = _utc_now()
    count = 0

    rows = conn.execute(
        """SELECT ncs.*, po.sc_id, sc.requester_id
           FROM notification_custom_schedule ncs
           JOIN pos po ON po.po_id = ncs.entity_id
           JOIN sc_records sc ON sc.sc_id = po.sc_id
           WHERE ncs.entity_type = 'po'
             AND ncs.enabled = 1
             AND po.status IN ('active', 'finished')
           ORDER BY ncs.entity_id, ncs.id"""
    ).fetchall()

    for r in rows:
        schedule = dict(r)
        po_id = schedule["entity_id"]

        # Respect per-PO notification disabled flag
        entity_config = cfg.get_entity_config(conn, po_id)
        if entity_config is not None and not entity_config["enabled"]:
            continue

        if not _schedule_matches_today(schedule, today):
            continue

        # Build recipients (same pattern as thresholds.py)
        requester_id = schedule["requester_id"]
        to_ids = [requester_id]
        to_ids = list(dict.fromkeys([uid for uid in to_ids if uid]))

        cc_ids = entity_config["cc_user_ids"] if entity_config else []
        cc_ids = [uid for uid in cc_ids if uid and uid not in to_ids]

        # event_key includes the date → same date same schedule can't double-fire
        date_str = today.strftime("%Y-%m-%d")
        schedule_type = schedule["schedule_type"]
        event_key = f"schedule:{schedule['id']}:{schedule_type}:{date_str}"

        q.queue_custom_schedule(
            conn, "po", po_id, event_key, to_ids, cc_ids, timestamp
        )
        count += 1
        logger.info(
            "Custom schedule matched: PO %s, schedule_id=%s, type=%s, date=%s",
            po_id, schedule["id"], schedule_type, date_str,
        )

    return count


def _schedule_matches_today(schedule: dict, today: date) -> bool:
    """Return True if the schedule fires on `today`."""
    stype = schedule["schedule_type"]

    if stype == "monthly_day":
        day = schedule["day_of_month"]
        last_day = calendar.monthrange(today.year, today.month)[1]
        target = min(day, last_day)  # 31 in Feb → fires on 28/29
        return today.day == target

    if stype == "weekly_day":
        # weekday: 0=Monday…6=Sunday (Python date.weekday())
        return today.weekday() == schedule["weekday"]

    if stype == "monthly_weekday":
        return _matches_nth_weekday(
            today,
            schedule["weekday"],
            schedule["occurrence"],  # 'first','second','third','fourth','last'
        )

    return False


def _matches_nth_weekday(today: date, target_weekday: int, occurrence: str) -> bool:
    """Check if today is the Nth occurrence of target_weekday in its month."""
    if today.weekday() != target_weekday:
        return False

    if occurrence == "last":
        # Walk backward from the last day of the month to find the last
        # occurrence of target_weekday.
        last_day = calendar.monthrange(today.year, today.month)[1]
        last_date = date(today.year, today.month, last_day)
        days_back = (last_date.weekday() - target_weekday) % 7
        last_occurrence_day = last_day - days_back
        return today.day == last_occurrence_day

    # For 'first'/'second'/'third'/'fourth': count occurrences
    first_day = date(today.year, today.month, 1)
    days_until_first = (target_weekday - first_day.weekday()) % 7
    first_occurrence_day = 1 + days_until_first

    occurrence_num = ((today.day - first_occurrence_day) // 7) + 1
    occ_map = {"first": 1, "second": 2, "third": 3, "fourth": 4}
    return occurrence_num == occ_map.get(occurrence, -1)
