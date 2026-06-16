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
        assert "150,000.00" in body
        assert "IT equipment" in body
        assert "Approved" in body  # status badge (English)

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
        assert "80,000.00" in body
        # Should NOT contain SC-specific labels
        assert "SC No" not in body
        assert "Service Period" not in body  # SC-specific

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
        assert "50,000.00" in body
        assert "Confirmed Amount" in body
        # Should NOT contain SC-specific labels
        assert "SC No" not in body
        assert "Service Period" not in body  # SC-specific

    def test_gr_shows_estimated_amount_when_no_con_value(self):
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
        assert "30,000.00" in body
        assert "Estimated Amount" in body

    def test_early_stage_transitions_show_placeholder_for_formal_numbers(self):
        """In early stages (create, submit, confirm), formal numbers may not
        be assigned yet — the field row appears but shows '-' placeholder
        instead of the number value."""
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
                # Label is always present (complete field display)
                assert label in body, (
                    f"{label} should appear for {entity_type} {event_key}"
                )
                # But the formal number value should NOT appear
                assert entity_info[list(entity_info.keys())[0]] not in body, (
                    f"Formal number value should NOT appear for {entity_type} {event_key}"
                )

    def test_missing_optional_fields_show_placeholder(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-002",
            "event_type": "status_change",
            "event_key": "finish",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {"status": "finished"}  # no po_no, no po_amount
        body = templates.build_body(entry, entity_info, {})
        # Fields with missing values show "-"
        assert "PO No" in body  # label always present
        assert "Finished" in body  # status badge contains English label


class TestBuildSubject:
    def test_status_change_subject(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "status_change",
            "event_key": "submit",
        }
        subject = templates.build_subject(entry, {})
        assert "[POMP] PO PO-001 Submitted" == subject

    def test_threshold_date_subject(self):
        entry = {
            "entity_type": "sc",
            "entity_id": "SC-001",
            "event_type": "threshold_date",
            "event_key": "threshold_date:3m",
        }
        entity_info = {"sc_no": "SC-2026-001"}
        subject = templates.build_subject(entry, entity_info)
        assert "SC-2026-001" in subject
        assert "3" in subject
        assert "Contract Expiring" in subject


class TestDescribeEvent:
    def test_status_change_event(self):
        assert "Submitted" == templates._describe_event("status_change", "submit")
        assert "Approved" == templates._describe_event("status_change", "approve")
        assert "Denied" == templates._describe_event("status_change", "deny")
        assert "Finished" == templates._describe_event("status_change", "finish")

    def test_threshold_date_event(self):
        result = templates._describe_event("threshold_date", "threshold_date:6m")
        assert "Contract Expiry" in result
        assert "6" in result

    def test_threshold_amount_event(self):
        result = templates._describe_event("threshold_amount", "threshold_amount:10%")
        assert "Budget Exhaustion" in result
        assert "10" in result

    def test_custom_schedule_event(self):
        result = templates._describe_event("custom_schedule", "schedule:1:monthly_day:2026-06-15")
        assert "Monthly Reminder" == result

        result2 = templates._describe_event("custom_schedule", "schedule:2:weekly_day:2026-06-10")
        assert "Weekly Reminder" == result2


class TestChildGrTable:
    def test_child_gr_table_renders(self):
        child_grs = [
            {
                "gr_no": "GR-2026-001",
                "estimated_amount": 30000,
                "con_value": 32000,
                "goods_service_description": "Software development",
                "delivery_from": "2026-01-01",
                "delivery_to": "2026-06-30",
                "status": "approved",
            },
            {
                "gr_no": "GR-2026-002",
                "estimated_amount": 15000,
                "con_value": None,
                "goods_service_description": "Hardware purchase",
                "delivery_from": None,
                "delivery_to": None,
                "status": "pending",
            },
        ]
        html = templates._child_gr_table(child_grs)
        assert "Related GRs (2)" in html
        assert "GR-2026-001" in html
        assert "GR-2026-002" in html
        assert "30,000.00" in html
        assert "32,000.00" in html
        assert "Software development" in html
        assert "Hardware purchase" in html
        assert "Approved" in html
        assert "Pending" in html

    def test_po_body_shows_child_gr_section(self):
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
            "child_grs": [
                {
                    "gr_no": "GR-2026-001",
                    "estimated_amount": 20000,
                    "con_value": 21000,
                    "goods_service_description": "Service A",
                    "delivery_from": "2026-01-01",
                    "delivery_to": "2026-03-31",
                    "status": "approved",
                },
            ],
        }
        body = templates.build_body(entry, entity_info, {})
        assert "Related GRs (1)" in body
        assert "GR-2026-001" in body
        assert "20,000.00" in body
        assert "Service A" in body

    def test_po_body_without_child_grs_omits_section(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-002",
            "event_type": "status_change",
            "event_key": "finish",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {
            "po_no": "PO-2026-002",
            "po_amount": 50000,
            "status": "finished",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "Related GRs" not in body


class TestFmtDatetime:
    def test_formats_iso_with_timezone(self):
        result = templates._fmt_datetime("2026-06-16T02:34:12+00:00")
        assert result == "2026-06-16 10:34:12"

    def test_formats_iso_with_microseconds(self):
        result = templates._fmt_datetime("2026-06-16T02:34:12.333756+00:00")
        assert result == "2026-06-16 10:34:12"

    def test_formats_iso_with_z_suffix(self):
        result = templates._fmt_datetime("2026-01-15T10:00:00Z")
        assert result == "2026-01-15 18:00:00"

    def test_returns_empty_for_none(self):
        assert templates._fmt_datetime(None) == ""

    def test_returns_empty_for_empty_string(self):
        assert templates._fmt_datetime("") == ""

    def test_preserves_non_iso_value(self):
        result = templates._fmt_datetime("2026-06-16")
        assert result == "2026-06-16"
