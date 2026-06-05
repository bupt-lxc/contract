"""Tests for notification email templates — build_body / build_subject."""

from sc_gr_app.notification import templates


class TestBuildBody:
    def test_sc_body_shows_sc_fields(self):
        entry = {
            "entity_type": "sc",
            "entity_id": "SC-001",
            "event_type": "status_change",
            "event_key": "approve",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "sc_no": "SC-2026-001",
            "sc_amount": 150000,
            "description": "IT equipment",
            "status": "approved",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "SC-2026-001" in body
        assert "SC No" in body
        assert "150000" in body
        assert "IT equipment" in body
        assert "approved" in body

    def test_po_body_shows_po_fields_not_sc_fields(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "status_change",
            "event_key": "finish",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "po_no": "PO-2026-001",
            "po_amount": 80000,
            "status": "finished",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "PO-2026-001" in body
        assert "PO No" in body
        assert "80000" in body
        # Should NOT contain SC-specific labels
        assert "SC No" not in body
        assert "Description" not in body

    def test_gr_body_shows_gr_fields_not_sc_fields(self):
        entry = {
            "entity_type": "gr",
            "entity_id": "GR-001",
            "event_type": "status_change",
            "event_key": "approve",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "gr_no": "GR-2026-001",
            "con_value": 50000,
            "estimated_amount": 45000,
            "status": "approved",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "GR-2026-001" in body
        assert "GR No" in body
        assert "50000" in body
        assert "Gross Cost" in body
        # Should NOT contain SC-specific labels
        assert "SC No" not in body
        assert "Description" not in body

    def test_gr_falls_back_to_estimated_amount_when_no_con_value(self):
        entry = {
            "entity_type": "gr",
            "entity_id": "GR-002",
            "event_type": "status_change",
            "event_key": "create",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "gr_no": "GR-2026-002",
            "con_value": None,
            "estimated_amount": 30000,
            "status": "draft",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "Net Cost" in body
        assert "30000" in body

    def test_early_stage_transitions_skip_formal_numbers(self):
        """SC No / PO No / GR No should not appear in draft/admin-approve
        stage emails (create, submit, confirm — before pending)."""
        for entity_type, entity_id, entity_info, label in [
            ("sc", "SC-001", {"sc_no": "SC-2026-001", "sc_amount": 1000, "status": "draft"}, "SC No"),
            ("po", "PO-001", {"po_no": "PO-2026-001", "po_amount": 1000, "status": "draft"}, "PO No"),
            ("gr", "GR-001", {"gr_no": "GR-2026-001", "con_value": 1000, "status": "draft"}, "GR No"),
        ]:
            for event_key in ("create", "submit", "confirm"):
                entry = {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "event_type": "status_change",
                    "event_key": event_key,
                    "created_at": "2026-01-15T10:00:00Z",
                }
                body = templates.build_body(entry, entity_info, {})
                assert label not in body, (
                    f"{label} should NOT appear for {entity_type} {event_key}"
                )

    def test_missing_optional_fields_are_omitted(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-002",
            "event_type": "status_change",
            "event_key": "finish",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {"status": "finished"}  # no po_no, no po_amount
        body = templates.build_body(entry, entity_info, {})
        assert "PO No" not in body
        assert "Amount" not in body
        assert "finished" in body
