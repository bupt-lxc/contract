"""Tests for notification API bridge endpoints."""

import json

from sc_gr_app.api import bridge
from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services import notification_service


def _seed_user(conn, user_id, machine_id, role="requester", email=None):
    conn.execute(
        "INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, 'active', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')",
        (user_id, machine_id, f"User {user_id}", role, email or f"{user_id}@test.com"),
    )


def _seed_sc_and_po(conn, sc_id="SC1", po_id="PO1", requester_id="U1", sc_status="approved"):
    conn.execute(
        """INSERT OR REPLACE INTO sc_records (sc_id, requester_id, status, request_type, cost_center,
           sc_amount, service_period_start, service_period_end, description, created_by, created_at, updated_at, asset)
           VALUES (?, ?, ?, 'material', 'CC1', 100000, '2025-01-01', '2026-12-31', '', ?, '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z', 'N')""",
        (sc_id, requester_id, sc_status, requester_id),
    )
    conn.execute(
        "INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
        "VALUES ('V1', 'Vendor 1', 'General Service', 'U1', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO pos (po_id, sc_id, vendor_id, po_amount, status, created_at, updated_at) "
        "VALUES (?, ?, 'V1', 100000, 'activing', '2025-01-01T00:00:00Z', '2025-01-01T00:00:00Z')",
        (po_id, sc_id),
    )


class TestBridgeNotificationEndpoints:
    def test_get_po_notification_config(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            _seed_sc_and_po(conn, "SC1", "PO1", "U1")
            conn.execute(
                "INSERT INTO notification_config (entity_type, entity_id, enabled, cc_user_ids) VALUES ('po', 'PO1', 1, '[\"U2\"]')"
            )
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_po_notification_config({"po_id": "PO1"})
        assert result["ok"] is True
        assert result["data"]["enabled"] is True
        assert result["data"]["cc_user_ids"] == ["U2"]

    def test_get_po_notification_config_returns_defaults_for_unconfigured(self, monkeypatch, app_config):
        """When no PO-specific config exists, the API returns global defaults."""
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_po_notification_config({"po_id": "PO_NONE"})
        assert result["ok"] is True
        # Returns global defaults, not None
        assert result["data"] is not None
        assert result["data"]["enabled"] is True
        assert "cc_user_ids" in result["data"]
        assert "date_thresholds" in result["data"]
        assert "amount_thresholds" in result["data"]

    def test_save_po_notification_config(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            _seed_sc_and_po(conn, "SC1", "PO1", "U1")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.save_po_notification_config({
            "po_id": "PO1",
            "data": {"enabled": True, "cc_user_ids": ["U2"], "date_thresholds": [6], "amount_thresholds": [50]}
        })
        assert result["ok"] is True

        # Verify it was saved
        verify = api.get_po_notification_config({"po_id": "PO1"})
        assert verify["data"]["date_thresholds"] == [6]

    def test_save_po_notification_config_denied_for_non_owner(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            _seed_user(conn, "U2", "2222222", "requester")
            _seed_sc_and_po(conn, "SC1", "PO1", "U1")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "2222222")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U2", "role": "requester", "machine_id": "2222222"})

        api = bridge.ApiBridge(app_config)
        result = api.save_po_notification_config({
            "po_id": "PO1",
            "data": {"enabled": True, "cc_user_ids": ["U2"]}
        })
        assert result["ok"] is False
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_get_notification_defaults_admin(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "admin")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "admin", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_notification_defaults()
        assert result["ok"] is True
        assert "notify.admin_recipients" in result["data"]

    def test_get_notification_defaults_allowed_for_requester(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.get_notification_defaults()
        assert result["ok"] is True
        assert "notify.admin_recipients" in result["data"]

    def test_save_notification_defaults_admin(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "admin")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "admin", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.save_notification_defaults({
            "data": {"admin_recipients": ["U1"]}
        })
        assert result["ok"] is True

    def test_save_notification_defaults_denied_for_requester(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.save_notification_defaults({
            "data": {"admin_recipients": ["U1"]}
        })
        assert result["ok"] is False
        assert result["error"]["code"] == "PERMISSION_DENIED"

    def test_list_notification_queue(self, monkeypatch, app_config):
        migrate(app_config)
        with connect(app_config) as conn:
            _seed_user(conn, "U1", "1234567", "requester")
            _seed_user(conn, "U2", "M2", "admin")
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (setting_key, setting_value, updated_at) VALUES (?, ?, ?)",
                ("notify.admin_recipients", json.dumps(["U2"]), "2025-01-01T00:00:00Z"),
            )
            conn.commit()

        with connect(app_config) as conn:
            conn.execute("BEGIN IMMEDIATE")
            notification_service.queue_status_change(
                conn, "sc", "SC1", "submit",
                {"requester_id": "U1"},
                {"user_id": "U1", "role": "requester", "machine_id": "1234567"},
            )
            conn.commit()

        monkeypatch.setattr(bridge, "get_7_digit_id", lambda: "1234567")
        monkeypatch.setattr(bridge, "get_user_by_machine_id",
                            lambda config, machine_id: {"user_id": "U1", "role": "requester", "machine_id": "1234567"})

        api = bridge.ApiBridge(app_config)
        result = api.list_notification_queue({"sc_id": "SC1"})
        assert result["ok"] is True
        assert result["data"]["total"] == 1
