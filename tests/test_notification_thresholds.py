"""Tests for daily threshold check logic — PO-based."""

import json
from datetime import date, timedelta

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.notification import thresholds

TIMESTAMP = "2025-01-01T00:00:00Z"


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'active', ?, ?)",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com", TIMESTAMP, TIMESTAMP),
    )


def _seed_sc(conn, sc_id, requester_id, status="approved", sc_amount=100000, service_period_end=None):
    conn.execute(
        """INSERT OR REPLACE INTO sc_records (sc_id, requester_id, status, request_type, cost_center,
           sc_amount, service_period_start, service_period_end, description, created_by, created_at, updated_at)
           VALUES (?, ?, ?, 'material', 'CC1', ?, '2025-01-01', ?, '', ?, ?, ?)""",
        (sc_id, requester_id, status, sc_amount, service_period_end or "2026-12-31", requester_id, TIMESTAMP, TIMESTAMP),
    )


def _seed_vendor(conn, vendor_id="V1"):
    conn.execute(
        """INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
           VALUES (?, ?, 'General Service', 'U1', ?, ?)""",
        (vendor_id, f"Vendor {vendor_id}", TIMESTAMP, TIMESTAMP),
    )


def _seed_po(conn, po_id="PO1", sc_id="SC1", po_amount=100000, status="active", contract_to=None):
    conn.execute(
        """INSERT OR IGNORE INTO pos (po_id, sc_id, vendor_id, po_amount, status, contract_to, created_at, updated_at)
           VALUES (?, ?, 'V1', ?, ?, ?, ?, ?)""",
        (po_id, sc_id, po_amount, status, contract_to, TIMESTAMP, TIMESTAMP),
    )


def _seed_gr(conn, gr_id, po_id="PO1", estimated_amount=80000, con_value=80000, status="approved"):
    conn.execute(
        """INSERT INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
           status, created_by, created_at, approved_by, approved_at)
           VALUES (?, ?, ?, 'U1', ?, ?, ?, 'U1', ?,
                   CASE WHEN ? = 'approved' THEN 'U1' ELSE NULL END,
                   CASE WHEN ? = 'approved' THEN ? ELSE NULL END)""",
        (gr_id, None, po_id, estimated_amount, con_value, status, TIMESTAMP, status, status, TIMESTAMP),
    )


class TestDateThresholds:
    def test_fires_when_below_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            # Contract end date is 5 months from now -- should trigger 6m threshold
            end_date = date.today() + timedelta(days=150)
            _seed_vendor(conn, "V1")
            _seed_sc(conn, "SC1", "U1")
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert date_count == 1  # 5 months < 6 months threshold
            assert amount_count == 0

            # Verify sent_threshold recorded
            sent = conn.execute(
                "SELECT * FROM notification_sent_threshold WHERE entity_id = 'PO1' AND event_key = 'threshold_date:6m'"
            ).fetchone()
            assert sent is not None

            # Verify queue entry
            queue_row = conn.execute(
                "SELECT * FROM notification_queue WHERE entity_id = 'PO1' AND event_key = 'threshold_date:6m'"
            ).fetchone()
            assert queue_row is not None

    def test_skips_when_above_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            # Contract end date is 12 months from now
            end_date = date.today() + timedelta(days=365)
            _seed_vendor(conn, "V1")
            _seed_sc(conn, "SC1", "U1")
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert date_count == 0

    def test_does_not_fire_twice(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            end_date = date.today() + timedelta(days=150)
            _seed_vendor(conn, "V1")
            _seed_sc(conn, "SC1", "U1")
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            # Pre-record that 6m threshold was already sent
            conn.execute(
                "INSERT INTO notification_sent_threshold (entity_type, entity_id, event_key, sent_at) "
                "VALUES ('po', 'PO1', 'threshold_date:6m', ?)",
                (TIMESTAMP,),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, _ = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert date_count == 0  # Already sent, skip


class TestAmountThresholds:
    def test_fires_when_below_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            _seed_sc(conn, "SC1", "U1")
            _seed_vendor(conn, "V1")
            # contract_to required for threshold scanning
            end_date = date.today() + timedelta(days=365)
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            # Create approved GR consuming 80% of PO amount (20% remaining)
            _seed_gr(conn, "GR1", "PO1", estimated_amount=80000, con_value=80000, status="approved")
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert amount_count == 1  # 20% remaining triggers threshold

            sent = conn.execute(
                "SELECT event_key FROM notification_sent_threshold WHERE entity_id = 'PO1' "
                "AND event_key LIKE 'threshold_amount:%'"
            ).fetchone()
            assert sent is not None
            # 20% remaining is below 50%, 30% -- fires tightest: 30%
            assert sent["event_key"] == "threshold_amount:30%"

    def test_skips_when_above_threshold(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            _seed_sc(conn, "SC1", "U1")
            _seed_vendor(conn, "V1")
            end_date = date.today() + timedelta(days=365)
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            # 60% remaining -- above all thresholds (50%, 30%, 10%)
            _seed_gr(conn, "GR1", "PO1", estimated_amount=40000, con_value=40000, status="approved")
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert amount_count == 0


class TestDisabledConfig:
    def test_skips_when_disabled(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), TIMESTAMP),
            )
            end_date = date.today() + timedelta(days=150)
            _seed_vendor(conn, "V1")
            _seed_sc(conn, "SC1", "U1")
            _seed_po(conn, "PO1", "SC1", po_amount=100000, status="active", contract_to=end_date.isoformat())
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled) VALUES ('po', 'PO1', 0)"
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            date_count, amount_count = thresholds.check_all_active_pos(conn)
            conn.commit()
            assert date_count == 0
            assert amount_count == 0
