"""Email subject and body templates (English) — simplified two-table format.

All email types (status_change, threshold_date, threshold_amount,
custom_schedule, monthly_summary) share a unified HTML template with:
  - Simple two-table layout (Notification Info + Detail Info)
  - Human-readable event labels (no raw event_key exposure)
  - Plain-text status display
"""

import re

from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# CSS constants — kept for monthly summary shell
# ---------------------------------------------------------------------------

_PAGE_STYLE = (
    "background-color:#f0f2f5;padding:24px 0;font-family:-apple-system,BlinkMacSystemFont,"
    "'Segoe UI',Roboto,'Helvetica Neue',Arial,'Microsoft YaHei',sans-serif;"
    "font-size:14px;color:#333;line-height:1.6"
)
_CONTAINER_STYLE = (
    "max-width:640px;margin:0 auto;background:#fff;border-radius:8px;"
    "box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden"
)
_HEADER_STYLE = (
    "background-color:#1a73e8;padding:28px 32px;color:#fff;text-align:center"
)
_HEADER_TITLE_STYLE = "font-size:18px;font-weight:700;margin:0;letter-spacing:0.5px"
_HEADER_SUBTITLE_STYLE = "font-size:13px;margin:6px 0 0 0;opacity:0.85"
_BODY_STYLE = "padding:24px 32px"
_SECTION_STYLE = (
    "margin-bottom:20px;border:1px solid #e8eaed;border-radius:6px;overflow:hidden"
)
_TABLE_STYLE = "width:100%;border-collapse:collapse;font-size:14px"
_TH_STYLE = (
    "padding:10px 16px;text-align:left;font-weight:500;color:#5f6368;"
    "background-color:#fafafa;border-bottom:1px solid #e8eaed;width:140px"
)
_TD_STYLE = "padding:10px 16px;border-bottom:1px solid #f0f0f0;color:#333"
_FOOTER_STYLE = (
    "padding:16px 32px;background-color:#fafafa;border-top:1px solid #e8eaed;"
    "font-size:12px;color:#9aa0a6;text-align:center"
)

# ---------------------------------------------------------------
# Labels
# ---------------------------------------------------------------

_STATUS_LABELS: dict[str, str] = {
    "draft": "Draft",
    "pending": "Pending",
    "manager_confirm": "To be confirm",
    "approved": "Approved",
    "denied": "Denied",
    "denied": "Denied",
    "finished": "Finished",
    "active": "Active",
    "po_pending": "PO Pending",
    "po_approved": "PO Approved",
}

_TRANSITION_LABELS: dict[str, str] = {
    "create": "Created",
    "submit": "Submitted",
    "confirm": "Confirmed",
    "approve": "Approved",
    "deny": "Denied",
    "deny": "Denied",
    "finish": "Finished",
    "notify": "Notification",
}

_TYPE_LABELS: dict[str, str] = {"sc": "SC", "po": "PO", "gr": "GR"}

# ---------------------------------------------------------------
# Field exclusions and renames for entity detail rows
# ---------------------------------------------------------------

_SC_EXCLUDE = {
    # Budget-derived fields (shown in their own way or not needed)
    "consumed_amount", "sc_available_amount",
    "pending_total", "pending_total_incl_tax", "child_pos",
    # Timestamps not relevant in notification emails
    "created_at", "updated_at", "approved_at", "finished_at", "confirmed_at",
    "pending_date", "approved_date",
    # People already shown in Notification Info section
    "created_by", "approved_by",
}
_PO_EXCLUDE = {"consumed_amount", "pending_total", "pending_total_incl_tax",
               "open_po_amount", "active_date", "created_at", "updated_at"}
_GR_EXCLUDE = {"created_at", "pending_date", "approved_date", "denied_at", "finished_at", "confirmed_at"}

_GR_RENAMES = {
    "estimated_amount": "GR Application Amount (Net)",
    "gross_cost": "GR Application Amount (Gross)",
    "con_value": "GR Value",
}
_PO_RENAMES = {
    "pending_total": "Pending GR amount (Net)",
    "pending_total_incl_tax": "Pending GR amount (Gross)",
}

_SC_ORDER = ["sc_id", "sc_no", "requester_id", "request_type", "cost_center",
             "sc_amount", "currency", "service_period_start", "service_period_end",
             "description", "asset", "asset_nums", "internal_system_number"]
_PO_ORDER = ["po_id", "po_no", "sc_id", "requester_id", "vendor_id", "vendor_name",
             "po_amount", "cost_center", "contract_no", "contract_type",
             "contract_from", "contract_to", "contract_pos",
             "payment_frequency", "purchaser"]
_GR_ORDER = ["gr_id", "gr_no", "po_id", "requester_id",
             "estimated_amount", "gross_cost", "tax_rate", "con_value",
             "goods_service_description", "remark", "confirmation_name",
             "delivery_from", "delivery_to", "last_delivery"]

# ---------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------

def _abbreviate_name(name: str) -> str:
    """Format: 'Li, Xingchen (C/EV-L)' → 'LiXingchen', 'Liwei Zhou' → 'LiweiZhou'"""
    if not name:
        return "Unknown"
    # Strip trailing parenthetical content (e.g. cost center)
    name = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if "," in name:
        parts = [p.strip() for p in name.split(",", 1)]
        surname = parts[0]
        given = parts[1] if len(parts) > 1 else ""
        return f"{surname}{given}"
    parts = name.strip().split()
    if len(parts) >= 2:
        return f"{parts[0]}{''.join(parts[1:])}"
    return name


def _short_entity_id(entity_id: str) -> str:
    """Shorten entity ID for subject: 'SC-V2SE7PP-20260629-002' → 'SC 0629-002'"""
    m = re.match(r'^([A-Z]+)-.+?-(\d{4})(\d{2})(\d{2})-(\d+)$', entity_id)
    if m:
        return f"{m.group(1)} {m.group(3)}{m.group(4)}-{m.group(5)}"
    return entity_id


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


# ---------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------

def _fmt_amount(value) -> str:
    """Format a numeric amount with thousands separator, or return empty string."""
    if value is None:
        return ""
    try:
        n = float(value)
        return f"{n:,.2f}"
    except (ValueError, TypeError):
        return str(value)


def _fmt_period(start, end) -> str:
    """Format a date range."""
    s = start or ""
    e = end or ""
    if s and e:
        return f"{s} ~ {e}"
    if s or e:
        return f"{s}{e}"
    return ""


def _fmt_datetime(value) -> str:
    """Format an ISO 8601 UTC timestamp to China Standard Time (UTC+8), seconds precision."""
    if not value:
        return ""
    try:
        s = str(value)
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if "T" in s:
            date_part, time_part = s.split("T", 1)
            if "+" in time_part:
                time_part = time_part.split("+")[0]
            dt_parts = date_part.split("-")
            tm_parts = time_part.split(":")
            year, month, day = int(dt_parts[0]), int(dt_parts[1]), int(dt_parts[2])
            hour, minute = int(tm_parts[0]), int(tm_parts[1])
            second = int(float(tm_parts[2]))
            dt_utc = datetime(year, month, day, hour, minute, second)
            dt_cst = dt_utc + timedelta(hours=8)
            return dt_cst.strftime("%Y-%m-%d %H:%M:%S")
        return s
    except (ValueError, TypeError, IndexError):
        return str(value)


def _utc_now_cn() -> str:
    """Current time in China Standard Time (UTC+8)."""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def _now_iso() -> str:
    """Current timestamp in ISO format."""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


# ---------------------------------------------------------------
# Entity detail rows
# ---------------------------------------------------------------

def _entity_detail_rows(entity_type: str, entity_info: dict) -> list[tuple[str, str]]:
    """Return (label, value) pairs for entity detail table, filtered and renamed."""
    if entity_type == "sc":
        exclude = _SC_EXCLUDE
        renames = {}
        order = _SC_ORDER
    elif entity_type == "po":
        exclude = _PO_EXCLUDE
        renames = _PO_RENAMES
        order = _PO_ORDER
    else:  # gr
        exclude = _GR_EXCLUDE
        renames = _GR_RENAMES
        order = _GR_ORDER

    result = []
    seen = set()
    for key in order:
        if key in entity_info and key not in exclude and key not in seen:
            seen.add(key)
            label = renames.get(key, key.replace("_", " ").title())
            val = entity_info[key]
            if key in ("sc_amount", "po_amount", "estimated_amount", "gross_cost",
                       "con_value", "consumed_amount", "open_po_amount",
                       "sc_available_amount", "pending_total", "pending_total_incl_tax"):
                val = _fmt_amount(val)
            elif key in ("service_period_start", "service_period_end",
                        "contract_from", "contract_to", "delivery_from",
                        "delivery_to", "last_delivery"):
                val = _fmt_datetime(val)
            elif key == "status":
                if val == "manager_confirm":
                    val = "To be confirm"
                else:
                    val = _STATUS_LABELS.get(val, val)
            result.append((label, val))

    for key, value in entity_info.items():
        if key.startswith("_") or key in exclude or key in seen:
            continue
        seen.add(key)
        label = renames.get(key, key.replace("_", " ").title())
        if key == "status":
            if value == "manager_confirm":
                value = "To be confirm"
            else:
                value = _STATUS_LABELS.get(value, value)
        result.append((label, value))

    return result


# ---------------------------------------------------------------
# HTML shell (for monthly summary)
# ---------------------------------------------------------------

def _html_shell(*, title: str, subtitle: str, body: str) -> str:
    """Wrap body content in the unified email HTML template."""
    return (
        f'<!DOCTYPE html>'
        f'<html lang="en">'
        f'<head><meta charset="utf-8"></head>'
        f'<body style="{_PAGE_STYLE}">'
        f'<div style="{_CONTAINER_STYLE}">'
        f'<div style="{_HEADER_STYLE}">'
        f'<div style="{_HEADER_TITLE_STYLE}">{title}</div>'
        f'<div style="{_HEADER_SUBTITLE_STYLE}">{subtitle}</div>'
        f'</div>'
        f'<div style="{_BODY_STYLE}">'
        f'{body}'
        f'</div>'
        f'<div style="{_FOOTER_STYLE}">'
        f'This email is automatically sent by PO Management Platform. Please do not reply.<br>'
        f'Generated at: {_utc_now_cn()}'
        f'</div>'
        f'</div>'
        f'</body>'
        f'</html>'
    )


# ---------------------------------------------------------------
# Public API
# ---------------------------------------------------------------

def build_subject(entry: dict, entity_info: dict, actor_name: str = "") -> str:
    """Build email subject line.

    Format: [POMP] <action> <short_entity_id> from <name>
    Example: [POMP] Submitted SC 0629-002 from LiXingchen
    """
    entity_id = _short_entity_id(entry.get("entity_id", ""))
    event_type = entry.get("event_type", "")
    event_key = entry.get("event_key", "")

    if event_type == "status_change":
        action = _TRANSITION_LABELS.get(event_key, event_key)
    elif event_type == "threshold_date":
        months = event_key.replace("threshold_date:", "").replace("m", "")
        action = f"Contract Expiring <{months}m"
    elif event_type == "threshold_amount":
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        action = f"Budget Exhausting <{pct}%"
    elif event_type == "custom_schedule":
        action = "Scheduled Reminder"
    else:
        action = event_key

    abbr = _abbreviate_name(actor_name) if actor_name else "System"
    return f"[POMP] {action} {entity_id} from {abbr}"


def build_body(entry: dict, entity_info: dict, user_emails: dict,
               actor_name: str = "", requester_name: str = "",
               show_confirm_btn: bool = False) -> str:
    """Build the HTML email body using a simple two-table layout.

    Table 1 — Notification Info: Entity Type, Entity ID, Event, Operator, Status, Attachments
    Table 2 — Detail Info: All entity fields (filtered and renamed)
    """
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_type = entry.get("event_type", "")
    event_key = entry.get("event_key", "")

    type_label = _TYPE_LABELS.get(entity_type, entity_type)
    status_value = entity_info.get("status", "")
    if status_value == "manager_confirm":
        status_display = "To be confirm"
    else:
        status_display = _STATUS_LABELS.get(status_value, status_value)

    event_desc = _describe_event(event_type, event_key)

    attachments = entity_info.get("_attachments", [])
    attachment_str = ", ".join(attachments) if attachments else "None"

    # Table 1: Notification Info
    lines = []
    lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-bottom:20px">')
    lines.append('<tr><th colspan="2" style="background:#f5f5f5;padding:8px;text-align:left;border:1px solid #ddd">Notification Info</th></tr>')
    for label, value in [
        ("Entity Type", type_label),
        ("Entity ID", entity_id),
        ("Event", event_desc),
        ("Operator", actor_name or "-"),
        ("Status", status_display),
        ("Attachments", attachment_str),
    ]:
        lines.append(f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;width:160px">{label}</td><td style="padding:8px;border:1px solid #ddd">{value}</td></tr>')
    lines.append('</table>')

    # Table 2: Detail Info
    entity_rows = _entity_detail_rows(entity_type, entity_info)
    lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px">')
    lines.append('<tr><th colspan="2" style="background:#f5f5f5;padding:8px;text-align:left;border:1px solid #ddd">Detail Info</th></tr>')
    for label, value in entity_rows:
        display = str(value) if value is not None else "-"
        lines.append(f'<tr><td style="padding:8px;border:1px solid #ddd;font-weight:bold;width:180px">{label}</td><td style="padding:8px;border:1px solid #ddd">{display}</td></tr>')
    lines.append('</table>')

    # Table 3: Vendor Info (SC only)
    if entity_type == "sc":
        vendors = entity_info.get("_vendors")
        if vendors:
            lines.append('<table style="width:100%;border-collapse:collapse;font-family:Arial,sans-serif;font-size:14px;margin-top:20px">')
            lines.append('<tr><th colspan="6" style="background:#f5f5f5;padding:8px;text-align:left;border:1px solid #ddd">Vendor Info</th></tr>')
            lines.append('<tr style="background:#fafafa">'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Vendor ID</th>'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Vendor Name</th>'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Service Scope</th>'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Contact</th>'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Phone</th>'
                         '<th style="padding:8px;border:1px solid #ddd;text-align:left">Email</th>'
                         '</tr>')
            for v in vendors:
                lines.append('<tr>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("vendor_id", "-")}</td>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("vendor_name", "-")}</td>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("service_scope", "-")}</td>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("contact_person", "-")}</td>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("phone", "-")}</td>'
                             f'<td style="padding:8px;border:1px solid #ddd">{v.get("email", "-")}</td>'
                             '</tr>')
            lines.append('</table>')

    # ── CTA buttons ──────────────────────────────────────────────────
    lines.append(
        '<table style="width:100%;border-collapse:collapse;'
        'font-family:Arial,sans-serif;font-size:14px;margin-top:24px">'
        '<tr><td align="center" style="padding:4px">'
    )

    # Always show "Open in POMP" button
    open_url = f"pomp://{entity_type}/{entity_id}"
    lines.append(
        f'<a href="{open_url}" '
        f'style="display:inline-block;padding:12px 32px;'
        f'background-color:#1a73e8;color:#fff;'
        f'text-decoration:none;border-radius:6px;'
        f'font-size:16px;font-weight:600">'
        f'Open in POMP →</a>'
    )

    # Additional "Confirm" button for SC/GR submit events
    if show_confirm_btn:
        confirm_url = f"pomp://{entity_type}/{entity_id}/confirm"
        lines.append('&nbsp;&nbsp;')
        lines.append(
            f'<a href="{confirm_url}" '
            f'style="display:inline-block;padding:12px 32px;'
            f'background-color:#34a853;color:#fff;'
            f'text-decoration:none;border-radius:6px;'
            f'font-size:16px;font-weight:600">'
            f'Confirm this {entity_type.upper()} →</a>'
        )

    lines.append(
        '<p style="margin-top:12px;font-size:12px;color:#9aa0a6">'
        'Clicking this button will open PO Management Platform.'
        ' If the app is not running, please start POMP first.</p>'
        '</td></tr></table>'
    )

    return "\n".join(lines)


# ---------------------------------------------------------------
# Monthly summary (unchanged)
# ---------------------------------------------------------------

def build_monthly_summary_subject(year: int, month: int) -> str:
    """Subject line for the monthly PO summary email."""
    return f"[POMP] {year}-{month:02d} PO Monthly Summary — Remaining Amount & Contract Expiry"


def build_monthly_summary_body(
    requester_name: str,
    year: int,
    month: int,
    po_list: list[dict],
) -> str:
    """Build HTML body for the monthly PO summary sent to each requester.

    po_list items are dicts with keys:
        po_no, sc_no, vendor_name, po_amount, open_po_amount,
        contract_to, remaining_days, status
    """
    table_rows: list[str] = []
    for i, po in enumerate(po_list):
        po_no = po.get("po_no") or "-"
        sc_no = po.get("sc_no") or "-"
        vendor = po.get("vendor_name") or "-"
        po_amount = f"{po['po_amount']:,.0f}" if po.get("po_amount") else "-"
        open_amount = f"{po['open_po_amount']:,.0f}" if po.get("open_po_amount") else "-"
        contract_to = po.get("contract_to") or "-"
        remaining = po.get("remaining_days")
        remaining_str = f"{remaining} days" if remaining is not None else "-"
        status = _STATUS_LABELS.get(po.get("status") or "", po.get("status") or "-")

        row_style = ""
        if remaining is not None and remaining < 30:
            row_style = "background-color:#fef7e0"
        elif (
            po.get("open_po_amount") is not None
            and po.get("po_amount")
            and po["open_po_amount"] / po["po_amount"] < 0.1
        ):
            row_style = "background-color:#fce8e6"

        tr = (
            f'<tr style="{row_style}">'
            f'<td style="{_TD_STYLE}">{po_no}</td>'
            f'<td style="{_TD_STYLE}">{sc_no}</td>'
            f'<td style="{_TD_STYLE}">{vendor}</td>'
            f'<td style="{_TD_STYLE}">{po_amount}</td>'
            f'<td style="{_TD_STYLE}">{open_amount}</td>'
            f'<td style="{_TD_STYLE}">{contract_to}</td>'
            f'<td style="{_TD_STYLE}">{remaining_str}</td>'
            f'<td style="{_TD_STYLE}">{status}</td>'
            f'</tr>'
        )
        table_rows.append(tr)

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

    inner_body = (
        f'<p style="margin:0 0 16px 0">Hello {requester_name},</p>'
        f'<p style="margin:0 0 20px 0;color:#5f6368">'
        f'Below is your PO monthly summary for {year}-{month:02d}, including remaining amounts and contract expiry dates:'
        f'</p>'
        f'<div style="{_SECTION_STYLE}">'
        f'<table style="{_TABLE_STYLE}">'
        f'{header}'
        + "".join(table_rows) +
        f'</table>'
        f'</div>'
        f'{legend}'
    )

    return _html_shell(
        title=f"{year}-{month:02d} PO Monthly Summary",
        subtitle=f"Requester: {requester_name}",
        body=inner_body,
    )
