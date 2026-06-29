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
        assert "Sc No" in body
        assert "150,000.00" in body
        assert "IT equipment" in body
        assert "Approved" in body  # plain text status (English)

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
        assert "Po No" in body
        assert "80,000.00" in body
        # Should NOT contain SC-specific labels
        assert "Sc No" not in body
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
            "gross_cost": 47000,
            "status": "approved",
        }
        body = templates.build_body(entry, entity_info, {})
        assert "GR-2026-001" in body
        assert "Gr No" in body
        assert "50,000.00" in body
        assert "GR Application Amount (Gross)" in body
        assert "47,000.00" in body
        # Should NOT contain SC-specific labels
        assert "Sc No" not in body
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
        assert "GR Application Amount (Net)" in body

    def test_missing_optional_fields_omitted_from_detail(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-002",
            "event_type": "status_change",
            "event_key": "finish",
            "created_at": "2026-01-15T10:00:00Z",
        }
        entity_info = {"status": "finished", "po_id": "PO-002"}
        body = templates.build_body(entry, entity_info, {})
        # Fields present in entity_info are shown
        assert "Po Id" in body  # po_id is in entity_info and not excluded
        assert "Finished" in body  # status label in Notification Info table
        # Fields not in entity_info are omitted (no placeholder rows)
        assert "Po No" not in body  # po_no not in entity_info, so not shown


class TestBuildSubject:
    def test_status_change_subject(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "status_change",
            "event_key": "submit",
        }
        subject = templates.build_subject(entry, {})
        assert subject == "[POMP] Submitted PO-001 from System"

    def test_threshold_date_subject(self):
        entry = {
            "entity_type": "sc",
            "entity_id": "SC-001",
            "event_type": "threshold_date",
            "event_key": "threshold_date:3m",
        }
        entity_info = {"sc_no": "SC-2026-001"}
        subject = templates.build_subject(entry, entity_info)
        assert "<3m" in subject
        assert "Contract Expiring" in subject
        assert "SC" in subject
        assert "SC-001" in subject
        assert "from System" in subject


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
