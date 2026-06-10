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
        assert "SC 编号" in body
        assert "150,000.00" in body
        assert "IT equipment" in body
        assert "已批准" in body  # status badge (Chinese)

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
        assert "PO 编号" in body
        assert "80,000.00" in body
        # Should NOT contain SC-specific labels
        assert "SC 编号" not in body
        assert "服务期间" not in body  # SC-specific

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
        assert "GR 编号" in body
        assert "50,000.00" in body
        assert "确认金额" in body
        # Should NOT contain SC-specific labels
        assert "SC 编号" not in body
        assert "服务期间" not in body  # SC-specific

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
        assert "预估金额" in body

    def test_early_stage_transitions_show_placeholder_for_formal_numbers(self):
        """In early stages (create, submit, confirm), formal numbers may not
        be assigned yet — the field row appears but shows '-' placeholder
        instead of the number value."""
        for entity_type, entity_id, entity_info, label in [
            ("sc", "SC-001", {"sc_no": "SC-2026-001", "sc_amount": 1000, "status": "draft"}, "SC 编号"),
            ("po", "PO-001", {"po_no": "PO-2026-001", "po_amount": 1000, "status": "draft"}, "PO 编号"),
            ("gr", "GR-001", {"gr_no": "GR-2026-001", "con_value": 1000, "status": "draft"}, "GR 编号"),
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
        assert "PO 编号" in body  # label always present
        assert "已" in body  # status badge contains Chinese label


class TestBuildSubject:
    def test_status_change_subject(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "status_change",
            "event_key": "submit",
        }
        subject = templates.build_subject(entry, {})
        assert "[Contract] PO PO-001 已提交" == subject

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
        assert "个月" in subject
        assert "合同即将到期" in subject


class TestDescribeEvent:
    def test_status_change_event(self):
        assert "已提交" == templates._describe_event("status_change", "submit")
        assert "已批准" == templates._describe_event("status_change", "approve")
        assert "已拒绝" == templates._describe_event("status_change", "deny")
        assert "已完成" == templates._describe_event("status_change", "finish")

    def test_threshold_date_event(self):
        result = templates._describe_event("threshold_date", "threshold_date:6m")
        assert "合同到期提醒" in result
        assert "6" in result
        assert "个月" in result

    def test_threshold_amount_event(self):
        result = templates._describe_event("threshold_amount", "threshold_amount:10%")
        assert "预算耗尽提醒" in result
        assert "10" in result

    def test_custom_schedule_event(self):
        result = templates._describe_event("custom_schedule", "schedule:1:monthly_day:2026-06-15")
        assert "每月定期提醒" == result

        result2 = templates._describe_event("custom_schedule", "schedule:2:weekly_day:2026-06-10")
        assert "每周定期提醒" == result2
