# Email I18n + Time Format + PO Contract Optional + Batch Button Role Hide

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Four independent changes: English email labels, readable timestamps in emails, optional PO contract_no, and hide batch confirm/approve for requesters.

**Architecture:** All changes are localized — templates.py for email i18n + time formatting, PoFormDialog.vue for contract_no optional, ScListView.vue and GrListView.vue for batch button role gating. No backend logic changes.

**Tech Stack:** Python 3.11, Vue 3 + Element Plus

---

### Task 1: Email labels → English — dictionaries, shell, subjects, event descriptions

**Files:**
- Modify: `sc_gr_app/notification/templates.py`

- [ ] **Step 1: Change `_STATUS_LABELS` dictionary**

Replace lines 77-89:

```python
_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "pending": "Pending",
    "manager_confirm": "Manager Confirm",
    "approved": "Approved",
    "denied": "Denied",
    "closed": "Closed",
    "finished": "Finished",
    "cancelled": "Cancelled",
    "activing": "Activing",
    "po_pending": "PO Pending",
    "po_approved": "PO Approved",
}
```

- [ ] **Step 2: Change `_TRANSITION_LABELS` dictionary**

Replace lines 105-114:

```python
_TRANSITION_LABELS: dict[str, str] = {
    "create": "Created",
    "submit": "Submitted",
    "confirm": "Confirmed",
    "approve": "Approved",
    "deny": "Denied",
    "close": "Closed",
    "finish": "Finished",
    "cancel": "Cancelled",
}
```

- [ ] **Step 3: Change `_describe_event` function**

Replace lines 134-152:

```python
def _describe_event(event_type: str, event_key: str) -> str:
    """Map internal event_key to a human-readable label."""
    if event_type == "status_change":
        return _TRANSITION_LABELS.get(event_key, event_key)

    if event_type == "threshold_date":
        months = event_key.replace("threshold_date:", "").replace("m", "")
        return f"Contract Expiry: Less than {months} months remaining"

    if event_type == "threshold_amount":
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        return f"Budget Exhaustion: Less than {pct}% remaining"

    if event_type == "custom_schedule":
        return _describe_schedule(event_key)

    return event_key
```

- [ ] **Step 4: Change `_describe_schedule` function**

Replace lines 155-167:

```python
def _describe_schedule(event_key: str) -> str:
    parts = event_key.split(":")
    if len(parts) < 4 or parts[0] != "schedule":
        return "Scheduled Reminder"
    stype = parts[2]
    type_labels = {
        "monthly_day": "Monthly Reminder",
        "monthly_weekday": "Monthly Weekday Reminder",
        "weekly_day": "Weekly Reminder",
    }
    return type_labels.get(stype, "Scheduled Reminder")
```

- [ ] **Step 5: Change `_html_shell` — lang attribute and footer**

Replace lines 479 and 493-495:

```python
# Line 479: lang attribute
f'<html lang="en">'

# Lines 493-495: footer text
f'<div style="{_FOOTER_STYLE}">'
f'This email is automatically sent by PO Management Platform. Please do not reply.<br>'
f'Generated at: {_utc_now_cn()}'
f'</div>'
```

- [ ] **Step 6: Change `build_subject` function**

Replace lines 507-534:

```python
def build_subject(entry: dict, entity_info: dict) -> str:
    """Build email subject line."""
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry["event_key"]
    event_type = entry.get("event_type", "")

    type_label = _TYPE_LABELS.get(entity_type, entity_type)

    if event_type == "status_change":
        label = _TRANSITION_LABELS.get(event_key, event_key)
        return f"[POMP] {type_label} {entity_id} {label}"

    if event_type == "threshold_date":
        sc_no = entity_info.get("sc_no") or entity_id
        months = event_key.replace("threshold_date:", "").replace("m", "")
        return f"[POMP] SC {sc_no} Contract Expiring — Less than {months} months"

    if event_type == "threshold_amount":
        sc_no = entity_info.get("sc_no") or entity_id
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        return f"[POMP] SC {sc_no} Budget Exhausting — Less than {pct}%"

    if event_type == "custom_schedule":
        po_no = entity_info.get("po_no") or entity_id
        return f"[POMP] PO {po_no} Scheduled Reminder"

    return f"[POMP] {type_label} {entity_id} — {event_key}"
```

- [ ] **Step 7: Change highlight box message in `build_body`**

Replace line 559-560 (`_highlight_box` call):

```python
        highlight = _highlight_box(
            f"⚠️ <b>{subtitle}</b> — Please handle promptly to avoid business impact."
        )
```

- [ ] **Step 8: Change notification info section labels in `build_body`**

Replace lines 565-573 (the `status_rows` block):

```python
    status_value = _status_badge(entity_info.get("status") or "")
    status_rows = [
        _field("Notification Type", type_label, alt=False),
        _field("Entity ID", entity_id, alt=True),
        _field("Event", subtitle, alt=False),
        _field("Current Status", status_value, alt=True),
    ]
    if event_type == "status_change":
        status_rows.append(_field("Operator", actor_name or "System", alt=False))
    status_rows.append(_field("Trigger Time", entry.get("created_at") or "", alt=len(status_rows) % 2 == 0))
```

- [ ] **Step 9: Change section titles in `build_body`**

Replace section title strings (around lines 605-608):

```python
        _section("Notification Info", status_rows),
        _section("Reminder Plan", schedule_rows) if schedule_rows else "",
        _section(f"{type_label} Details", entity_rows),
```

- [ ] **Step 10: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: change email labels from Chinese to English — dicts, subjects, shell"
```

### Task 2: Email labels → English — entity fields, child tables, monthly summary

**Files:**
- Modify: `sc_gr_app/notification/templates.py`

- [ ] **Step 1: Change `_sc_fields` — all Chinese labels to English**

Replace lines 219-241 (row labels inside `_sc_fields`):

```python
    rows.append(row("SC No", sc_no))
    rows.append(row("Requester", requester_name or (info.get("requester_id") or "")))
    rows.append(row("Request Type", info.get("request_type") or ""))
    rows.append(row("Cost Center", info.get("cost_center") or ""))
    rows.append(row("SC Amount", _fmt_amount(info.get("sc_amount"))))
    if "consumed_amount" in info:
        rows.append(row("Consumed Amount", _fmt_amount(info.get("consumed_amount"))))
    if "sc_available_amount" in info:
        rows.append(row("Available Amount", _fmt_amount(info.get("sc_available_amount"))))
    rows.append(row("Service Period", _fmt_period(
        info.get("service_period_start"), info.get("service_period_end")
    )))
    rows.append(row("Description", info.get("description") or ""))
    rows.append(row("Asset", info.get("asset") or ""))
    rows.append(row("Asset Numbers", info.get("asset_nums") or ""))
    rows.append(row("Internal System Number", info.get("internal_system_number") or ""))

    # Dates
    rows.append(row("Created At", info.get("created_at") or ""))
    rows.append(row("Updated At", info.get("updated_at") or ""))
    rows.append(row("Pending Date", info.get("pending_date") or ""))
    rows.append(row("Approved Date", info.get("approved_date") or ""))
    rows.append(row("Closed Date", info.get("closed_at") or ""))
```

- [ ] **Step 2: Change `_po_fields` — all Chinese labels to English**

Replace lines 258-288 (row labels inside `_po_fields`):

```python
    po_no = (info.get("po_no") or "") if show_formal_number else ""
    rows.append(row("PO No", po_no))
    rows.append(row("Requester", requester_name or (info.get("requester_id") or "")))
    rows.append(row("Vendor", info.get("vendor_name") or ""))

    # Financial
    rows.append(row("PO Amount", _fmt_amount(info.get("po_amount"))))
    if "consumed_amount" in info:
        rows.append(row("Consumed Amount", _fmt_amount(info.get("consumed_amount"))))
    if "open_po_amount" in info:
        rows.append(row("Open PO Amount", _fmt_amount(info.get("open_po_amount"))))
    rows.append(row("Cost Center", info.get("cost_center") or ""))

    # Contract
    rows.append(row("Contract No", info.get("contract_no") or ""))
    rows.append(row("Contract Type", info.get("contract_type") or ""))
    rows.append(row("Contract Period", _fmt_period(
        info.get("contract_from"), info.get("contract_to")
    )))
    rows.append(row("Contract Pos.", info.get("contract_pos") or ""))

    # Payment
    rows.append(row("Payment Frequency", info.get("payment_frequency") or ""))

    # Personnel
    rows.append(row("Purchaser", info.get("purchaser") or ""))

    # Dates
    rows.append(row("Activing Date", info.get("activing_date") or ""))
    rows.append(row("Created At", info.get("created_at") or ""))
    rows.append(row("Updated At", info.get("updated_at") or ""))
```

- [ ] **Step 3: Change `_gr_fields` — all Chinese labels to English**

Replace lines 305-332 (row labels inside `_gr_fields`):

```python
    gr_no = (info.get("gr_no") or "") if show_formal_number else ""
    rows.append(row("GR No", gr_no))
    rows.append(row("Requester", requester_name or (info.get("requester_id") or "")))

    # Financial
    rows.append(row("Estimated Amount (Net)", _fmt_amount(info.get("estimated_amount"))))
    rows.append(row("Confirmed Amount (Tax incl.)", _fmt_amount(info.get("con_value"))))
    rows.append(row("VAT Rate (%)", info.get("tax_rate") or ""))

    # Description
    rows.append(row("Goods/Service Description", info.get("goods_service_description") or ""))
    rows.append(row("Remark", info.get("remark") or ""))

    # Confirmation
    rows.append(row("Confirmation Name", info.get("confirmation_name") or ""))

    # Delivery
    rows.append(row("Delivery Period", _fmt_period(
        info.get("delivery_from"), info.get("delivery_to")
    )))
    rows.append(row("Last Delivery", info.get("last_delivery") or ""))

    # Dates
    rows.append(row("Created At", info.get("created_at") or ""))
    rows.append(row("Pending Date", info.get("pending_date") or ""))
    rows.append(row("Approved Date", info.get("approved_date") or ""))
    rows.append(row("Cancelled At", info.get("cancelled_at") or ""))
    rows.append(row("Confirmed At", info.get("confirmed_at") or ""))
```

- [ ] **Step 4: Change `_child_po_table` — section title and column headers**

Replace section title (line 420) and header rows (lines 378-387):

```python
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">PO No</th>'
        f'<th style="{_TH_STYLE}">Vendor</th>'
        f'<th style="{_TH_STYLE}">PO Amount</th>'
        f'<th style="{_TH_STYLE}">Consumed</th>'
        f'<th style="{_TH_STYLE}">Open Amount</th>'
        f'<th style="{_TH_STYLE}">Contract End</th>'
        f'<th style="{_TH_STYLE}">Status</th>'
        f'</tr>'
    )

    # ...

    return _section(f"Related POs ({len(child_pos)})", [table])
```

- [ ] **Step 5: Change `_child_gr_table` — section title and column headers**

Replace section title (line 468) and header rows (lines 429-437):

```python
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">GR No</th>'
        f'<th style="{_TH_STYLE}">Estimated Amount (Net)</th>'
        f'<th style="{_TH_STYLE}">Confirmed Amount (Tax incl.)</th>'
        f'<th style="{_TH_STYLE}">Goods/Service Description</th>'
        f'<th style="{_TH_STYLE}">Delivery Period</th>'
        f'<th style="{_TH_STYLE}">Status</th>'
        f'</tr>'
    )

    # ...

    return _section(f"Related GRs ({len(child_grs)})", [table])
```

- [ ] **Step 6: Change `build_monthly_summary_subject`**

Replace lines 620-621:

```python
def build_monthly_summary_subject(year: int, month: int) -> str:
    """Subject line for the monthly PO summary email."""
    return f"[POMP] {year}-{month:02d} PO Monthly Summary — Remaining Amount & Contract Expiry"
```

- [ ] **Step 7: Change `build_monthly_summary_body` — all Chinese to English**

Replace the table headers, intro text, legend, and shell title/subtitle:

```python
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">PO No</th>'
        f'<th style="{_TH_STYLE}">SC No</th>'
        f'<th style="{_TH_STYLE}">Vendor</th>'
        f'<th style="{_TH_STYLE}">PO Amount</th>'
        f'<th style="{_TH_STYLE}">Remaining Amount</th>'
        f'<th style="{_TH_STYLE}">Contract End Date</th>'
        f'<th style="{_TH_STYLE}">Remaining Days</th>'
        f'<th style="{_TH_STYLE}">Status</th>'
        f'</tr>'
    )
```

```python
        remaining_str = f"{remaining} days" if remaining is not None else "-"
```

```python
    legend = (
        '<div style="margin-top:16px;font-size:12px;color:#5f6368">'
        '<span style="display:inline-block;width:12px;height:12px;'
        'background-color:#fef7e0;border:1px solid #f9ab00;margin-right:4px;vertical-align:middle"></span> '
        'Yellow = Contract expires in less than 30 days &nbsp;&nbsp;'
        '<span style="display:inline-block;width:12px;height:12px;'
        'background-color:#fce8e6;border:1px solid #d93025;margin-right:4px;vertical-align:middle"></span> '
        'Red = Budget remaining less than 10%'
        '</div>'
    )
```

```python
    inner_body = (
        f'<p style="margin:0 0 16px 0">Hello {requester_name},</p>'
        f'<p style="margin:0 0 20px 0;color:#5f6368">'
        f'Below is your PO monthly summary for {year}-{month:02d}, including remaining amounts and contract expiry dates:'
        f'</p>'
        # ... rest unchanged
    )
```

```python
    return _html_shell(
        title=f"{year}-{month:02d} PO Monthly Summary",
        subtitle=f"Requester: {requester_name}",
        body=inner_body,
    )
```

- [ ] **Step 8: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: change email entity fields, child tables, monthly summary labels to English"
```

### Task 3: Add `_fmt_datetime` helper and apply to timestamps

**Files:**
- Modify: `sc_gr_app/notification/templates.py`

- [ ] **Step 1: Add `_fmt_datetime` function after `_fmt_period` (after line 359)**

```python
def _fmt_datetime(value) -> str:
    """Format an ISO 8601 UTC timestamp to CST readable string (seconds precision)."""
    if not value:
        return "-"
    try:
        s = str(value)
        # Handle timestamps with or without timezone offset
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # Parse ISO 8601 to naive UTC, then add 8 hours for CST
        if "T" in s:
            date_part, time_part = s.split("T", 1)
            # Strip timezone from time part for parsing
            if "+" in time_part:
                time_part = time_part.split("+")[0]
            elif time_part.endswith("Z"):
                time_part = time_part[:-1]
            # Parse date and time
            from datetime import datetime, timezone, timedelta
            dt_parts = date_part.split("-")
            tm_parts = time_part.split(":")
            year, month, day = int(dt_parts[0]), int(dt_parts[1]), int(dt_parts[2])
            hour, minute, second = int(tm_parts[0]), int(tm_parts[1]), int(float(tm_parts[2]))
            dt_utc = datetime(year, month, day, hour, minute, second)
            dt_cst = dt_utc + timedelta(hours=8)
            return dt_cst.strftime("%Y-%m-%d %H:%M:%S")
        return s
    except (ValueError, TypeError, IndexError):
        return str(value)
```

- [ ] **Step 2: Apply `_fmt_datetime` to timestamp fields in `_sc_fields`**

Change lines 237-241 — wrap timestamp values with `_fmt_datetime`:

```python
    rows.append(row("Created At", _fmt_datetime(info.get("created_at"))))
    rows.append(row("Updated At", _fmt_datetime(info.get("updated_at"))))
    rows.append(row("Pending Date", _fmt_datetime(info.get("pending_date"))))
    rows.append(row("Approved Date", _fmt_datetime(info.get("approved_date"))))
    rows.append(row("Closed Date", _fmt_datetime(info.get("closed_at"))))
```

Also wrap the service period values (line 228-230):

```python
    rows.append(row("Service Period", _fmt_period(
        _fmt_datetime(info.get("service_period_start")),
        _fmt_datetime(info.get("service_period_end"))
    )))
```

- [ ] **Step 3: Apply `_fmt_datetime` to timestamp fields in `_po_fields`**

Change date rows (lines 286-288) and contract period (lines 274-276):

```python
    rows.append(row("Contract Period", _fmt_period(
        _fmt_datetime(info.get("contract_from")),
        _fmt_datetime(info.get("contract_to"))
    )))
    # ...
    rows.append(row("Activing Date", _fmt_datetime(info.get("activing_date"))))
    rows.append(row("Created At", _fmt_datetime(info.get("created_at"))))
    rows.append(row("Updated At", _fmt_datetime(info.get("updated_at"))))
```

- [ ] **Step 4: Apply `_fmt_datetime` to timestamp fields in `_gr_fields`**

Change date rows (lines 328-332) and delivery period (lines 322-323):

```python
    rows.append(row("Delivery Period", _fmt_period(
        _fmt_datetime(info.get("delivery_from")),
        _fmt_datetime(info.get("delivery_to"))
    )))
    rows.append(row("Last Delivery", _fmt_datetime(info.get("last_delivery")))

    rows.append(row("Created At", _fmt_datetime(info.get("created_at"))))
    rows.append(row("Pending Date", _fmt_datetime(info.get("pending_date"))))
    rows.append(row("Approved Date", _fmt_datetime(info.get("approved_date"))))
    rows.append(row("Cancelled At", _fmt_datetime(info.get("cancelled_at"))))
    rows.append(row("Confirmed At", _fmt_datetime(info.get("confirmed_at"))))
```

- [ ] **Step 5: Apply `_fmt_datetime` to trigger time in `build_body`**

Change line 573 (trigger time row):

```python
    status_rows.append(_field("Trigger Time", _fmt_datetime(entry.get("created_at")), alt=len(status_rows) % 2 == 0))
```

- [ ] **Step 6: Commit**

```bash
git add sc_gr_app/notification/templates.py
git commit -m "feat: add _fmt_datetime helper, format all timestamps as readable CST in emails"
```

### Task 4: Update tests for English labels and time format

**Files:**
- Modify: `tests/test_notification_templates.py`

- [ ] **Step 1: Update `TestBuildBody.test_sc_body_shows_sc_fields`**

Change Chinese label assertions to English (line 23: `"SC 编号"` → `"SC No"`, line 26: `"已批准"` → `"Approved"`):

```python
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
        assert "Approved" in body  # status badge
```

- [ ] **Step 2: Update `TestBuildBody.test_po_body_shows_po_fields_not_sc_fields`**

Change Chinese label assertions to English:

```python
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
```

- [ ] **Step 3: Update `TestBuildBody.test_gr_body_shows_gr_fields_not_sc_fields`**

Change Chinese label assertions to English:

```python
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
```

- [ ] **Step 4: Update `TestBuildBody.test_gr_shows_estimated_amount_when_no_con_value`**

Change Chinese label assertion:

```python
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
```

- [ ] **Step 5: Update `TestBuildBody.test_early_stage_transitions_show_placeholder_for_formal_numbers`**

Change Chinese label assertions to English:

```python
    def test_early_stage_transitions_show_placeholder_for_formal_numbers(self):
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
                assert label in body, (
                    f"{label} should appear for {entity_type} {event_key}"
                )
                assert entity_info[list(entity_info.keys())[0]] not in body, (
                    f"Formal number value should NOT appear for {entity_type} {event_key}"
                )
```

- [ ] **Step 6: Update `TestBuildBody.test_missing_optional_fields_show_placeholder`**

Change Chinese label assertion:

```python
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
```

- [ ] **Step 7: Update `TestBuildSubject.test_status_change_subject`**

```python
    def test_status_change_subject(self):
        entry = {
            "entity_type": "po",
            "entity_id": "PO-001",
            "event_type": "status_change",
            "event_key": "submit",
        }
        subject = templates.build_subject(entry, {})
        assert "[POMP] PO PO-001 Submitted" == subject
```

- [ ] **Step 8: Update `TestBuildSubject.test_threshold_date_subject`**

```python
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
```

- [ ] **Step 9: Update `TestDescribeEvent` class**

```python
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
```

- [ ] **Step 10: Update `TestChildGrTable` class**

```python
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
```

- [ ] **Step 11: Add `TestFmtDatetime` class at end of file**

```python
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

    def test_returns_dash_for_none(self):
        assert templates._fmt_datetime(None) == "-"

    def test_returns_dash_for_empty_string(self):
        assert templates._fmt_datetime("") == "-"

    def test_preserves_non_iso_value(self):
        result = templates._fmt_datetime("2026-06-16")
        assert result == "2026-06-16"
```

- [ ] **Step 12: Run tests to verify all pass**

```bash
uv run pytest tests/test_notification_templates.py -v
```

Expected: All tests PASS.

- [ ] **Step 13: Commit**

```bash
git add tests/test_notification_templates.py
git commit -m "test: update email template tests for English labels and time format"
```

### Task 5: PO Contract NO → optional

**Files:**
- Modify: `frontend/src/components/po/PoFormDialog.vue`

- [ ] **Step 1: Remove `prop="contract_no"` from the form item**

Change line 48 from:
```html
          <el-form-item :label="$t('po.contractNo')" prop="contract_no">
```
to:
```html
          <el-form-item :label="$t('po.contractNo')">
```

- [ ] **Step 2: Remove `contract_no` from the `rules` object**

Remove line 148:
```javascript
  contract_no: [{ required: true, message: t('po.contractNoRequired'), trigger: 'blur' }]
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/po/PoFormDialog.vue
git commit -m "feat: make PO Contract No optional (remove required validation)"
```

### Task 6: Hide batch confirm/approve buttons for requester — ScListView

**Files:**
- Modify: `frontend/src/views/ScListView.vue`

- [ ] **Step 1: Add `isAdmin` computed property**

Add after line 85 (after `const { t } = useI18n()`):

Import `computed` at line 66 — it is already imported as part of the existing imports `ref, computed, onMounted`.

Add this line after the existing variable declarations (around line 87):

```javascript
const isAdmin = computed(() => window.__currentUser?.role === 'admin')
```

- [ ] **Step 2: Add `&& isAdmin` to batch confirm button**

Change line 21 from:
```html
      <el-button v-if="selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
```
to:
```html
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
```

- [ ] **Step 3: Add `&& isAdmin` to batch approve button**

Change line 22 from:
```html
      <el-button v-if="selectedRows.some(r => r.status === 'pending')" size="small" type="success" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
```
to:
```html
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'pending')" size="small" type="success" @click="handleBatchApprove">{{ $t('batch.approve') }}</el-button>
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/views/ScListView.vue
git commit -m "feat: hide batch confirm and approve buttons for requester in SC list"
```

### Task 7: Hide batch confirm button for requester — GrListView

**Files:**
- Modify: `frontend/src/views/GrListView.vue`

- [ ] **Step 1: Add `isAdmin` computed property**

Add after line 141 (after `const { t } = useI18n()`):

```javascript
const isAdmin = computed(() => window.__currentUser?.role === 'admin')
```

`computed` is already imported at line 124.

- [ ] **Step 2: Add `&& isAdmin` to batch confirm button**

Change line 21 from:
```html
      <el-button v-if="selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
```
to:
```html
      <el-button v-if="isAdmin && selectedRows.some(r => r.status === 'manager_confirm')" size="small" type="primary" @click="handleBatchConfirm">{{ $t('batch.confirm') }}</el-button>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/views/GrListView.vue
git commit -m "feat: hide batch confirm button for requester in GR list"
```

---

### Final verification

- [ ] Run all tests: `uv run pytest -q`
- [ ] Check there are no other references to the changed Chinese label strings in the codebase:
  ```bash
  git grep "草稿\|待审批\|已批准\|此邮件由" -- '*.py' || echo "No remaining Chinese — OK"
  ```
