"""Tests for notification_service — queue writer and config CRUD."""

import json

from sc_gr_app.services import notification_service
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status) VALUES (?, ?, ?, ?, ?, 'active')",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com"),
    )


def _seed_sc(conn, sc_id, requester_id, status="approved", sc_amount=100000, service_period_end=None):
    conn.execute(
        """INSERT OR REPLACE INTO sc_records (sc_id, requester_id, status, request_type, cost_center,
           sc_amount, service_period_start, service_period_end, description, created_at, updated_at)
           VALUES (?, ?, ?, 'material', 'CC1', ?, '2025-01-01', ?, '', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')""",
        (sc_id, requester_id, status, sc_amount, service_period_end or "2026-12-31"),
    )


class TestQueueStatusChange:
    def test_writes_queue_entry_for_submit(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 1
            row = dict(rows[0])
            assert row["entity_type"] == "sc"
            assert row["entity_id"] == "SC1"
            assert row["event_type"] == "status_change"
            assert row["event_key"] == "submit"
            assert row["status"] == "pending"
            to_ids = json.loads(row["to_recipients"])
            assert "U2" in to_ids
            cc_ids = json.loads(row["cc_recipients"])
            assert "U1" in cc_ids

    def test_queue_write_uses_actor_keyword(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U2", "role": "admin", "machine_id": "M2"}
            notification_service.queue_status_change(conn, "sc", "SC1", "approve", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            row = dict(conn.execute("SELECT * FROM notification_queue").fetchone())
            to_ids = json.loads(row["to_recipients"])
            cc_ids = json.loads(row["cc_recipients"])
            assert "U1" in to_ids
            assert "U2" in cc_ids

    def test_skips_when_no_rules_configured(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            # Remove default GR transition rules seeded by migrate to test "no rules" path
            conn.execute("DELETE FROM app_settings WHERE setting_key = 'notify.transitions.gr'")
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "gr", "GR1", "approve", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 0

    def test_skips_when_no_to_recipients(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", "[]", "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 0

    def test_merges_per_sc_cc_list(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            _seed_user(conn, "U3", "M3", "requester")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids) VALUES ('sc', 'SC1', 1, ?)",
                (json.dumps(["U3"]),),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            row = dict(conn.execute("SELECT * FROM notification_queue").fetchone())
            cc_ids = json.loads(row["cc_recipients"])
            assert "U3" in cc_ids

    def test_duplicate_event_refreshes_existing_pending(self, app_config):
        """A second submit while the first is still pending should refresh the
        existing entry rather than being silently dropped (INSERT OR IGNORE)."""
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        entity = {"requester_id": "U1"}
        current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}

        # First submit
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 1
            first_ts = rows[0]["created_at"]

        # Second submit — same event, still pending
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute("SELECT * FROM notification_queue").fetchall()
            assert len(rows) == 1  # still one entry, not silently duplicated
            second_ts = rows[0]["created_at"]
            assert second_ts >= first_ts  # timestamp was refreshed

    def test_duplicate_event_inserts_when_previous_is_done(self, app_config):
        """When the previous entry is already processed (done/failed), a
        new submit should create a fresh entry."""
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        entity = {"requester_id": "U1"}
        current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}

        # First submit
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        # Mark as done (simulating notification script processed it)
        with connect(app_config) as conn:
            conn.execute(
                "UPDATE notification_queue SET status = 'done' WHERE entity_id = 'SC1'"
            )
            conn.commit()

        # Second submit after first was already processed
        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            conn.commit()

        with connect(app_config) as conn:
            rows = conn.execute(
                "SELECT * FROM notification_queue WHERE status = 'pending'"
            ).fetchall()
            assert len(rows) == 1  # new pending entry created



class TestScNotificationConfig:
    def test_save_and_get(self, app_config):
        migrate(app_config)
        data = {
            "enabled": True,
            "cc_user_ids": ["U2", "U3"],
            "date_thresholds": [6, 3],
            "amount_thresholds": [50, 10],
        }
        notification_service.save_sc_notification_config(app_config, "SC1", data)
        result = notification_service.get_sc_notification_config(app_config, "SC1")
        assert result == data

    def test_returns_defaults_for_unconfigured_sc(self, app_config):
        migrate(app_config)
        result = notification_service.get_sc_notification_config(app_config, "SC_NONE")
        assert result is not None
        assert result["enabled"] is True
        assert isinstance(result["cc_user_ids"], list)
        assert isinstance(result["date_thresholds"], list)
        assert isinstance(result["amount_thresholds"], list)

    def test_save_updates_existing(self, app_config):
        migrate(app_config)
        notification_service.save_sc_notification_config(app_config, "SC1", {"enabled": True, "cc_user_ids": [], "date_thresholds": [6], "amount_thresholds": [50]})
        notification_service.save_sc_notification_config(app_config, "SC1", {"enabled": False, "cc_user_ids": ["U1"], "date_thresholds": [3], "amount_thresholds": [30]})
        result = notification_service.get_sc_notification_config(app_config, "SC1")
        assert result["enabled"] is False
        assert result["cc_user_ids"] == ["U1"]


class TestNotificationDefaults:
    def test_save_and_get(self, app_config):
        migrate(app_config)
        data = {
            "admin_recipients": ["U2"],
            "transitions": {
                "sc": {"submit": {"to": ["notify.admin_recipients"], "cc": ["requester"]}},
                "po": {"create": {"to": ["notify.admin_recipients"], "cc": []}},
                "gr": {"create": {"to": ["notify.admin_recipients"], "cc": []}},
            },
            "default_cc": ["U3"],
            "date_thresholds": [6, 3, 1],
            "amount_thresholds": [50, 30],
        }
        notification_service.save_notification_defaults(app_config, data)
        result = notification_service.get_notification_defaults(app_config)
        assert result["notify.admin_recipients"] == ["U2"]
        assert result["notify.default_cc"] == ["U3"]
        assert result["notify.default_date_thresholds"] == [6, 3, 1]
        assert result["notify.default_amount_thresholds"] == [50, 30]

    def test_save_transitions_preserves_unknown_keys(self, app_config):
        """Saving partial transitions merges with existing DB rules,
        preserving transitions the caller does not supply."""
        migrate(app_config)

        # DB already has full transition rules from migration.
        # Save ONLY the 'submit' transition for SC — nothing else.
        partial = {
            "transitions": {
                "sc": {
                    "submit": {"to": ["requester"], "cc": []},
                },
            },
        }
        notification_service.save_notification_defaults(app_config, partial)

        result = notification_service.get_notification_defaults(app_config)
        sc_transitions = result["notify.transitions.sc"]

        # The supplied transition should use the new values.
        assert sc_transitions["submit"] == {"to": ["requester"], "cc": []}

        # Unspecified transitions must survive the merge.
        assert "confirm" in sc_transitions
        assert "approve" in sc_transitions
        assert "deny" in sc_transitions
        assert "close" in sc_transitions
        assert "revoke" in sc_transitions

        # PO/GR transitions should be untouched since we didn't send them.
        po_transitions = result["notify.transitions.po"]
        assert "create" in po_transitions
        assert "submit" in po_transitions
        assert "finish" in po_transitions

        gr_transitions = result["notify.transitions.gr"]
        assert "create" in gr_transitions
        assert "submit" in gr_transitions
        assert "confirm" in gr_transitions
        assert "approve" in gr_transitions
        assert "cancel" in gr_transitions
        assert "revoke" in gr_transitions


class TestListNotificationQueue:
    def test_list_with_filters(self, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "M1", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            entity = {"requester_id": "U1"}
            current_user = {"user_id": "U1", "role": "requester", "machine_id": "M1"}
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            notification_service.queue_status_change(conn, "sc", "SC1", "submit", entity, current_user)
            notification_service.queue_status_change(conn, "sc", "SC2", "submit", entity, current_user)
            conn.commit()

        result = notification_service.list_notification_queue(app_config)
        assert result["total"] == 2

        result = notification_service.list_notification_queue(app_config, sc_id="SC1")
        assert result["total"] == 1
