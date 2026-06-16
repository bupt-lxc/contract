"""Email subject and body templates (Chinese) — modern HTML design.

All email types (status_change, threshold_date, threshold_amount,
custom_schedule, monthly_summary) share a unified HTML template with:
  - Modern card-style layout with inline CSS
  - Complete entity field display (all DB columns)
  - Human-readable Chinese event labels (no raw event_key exposure)
  - Professional color-coded status badges
"""

from datetime import datetime, timezone, timedelta

# ---------------------------------------------------------------------------
# CSS constants — inline styles for email client compatibility
# ---------------------------------------------------------------------------

# Page background + container
_PAGE_STYLE = (
    "background-color:#f0f2f5;padding:24px 0;font-family:-apple-system,BlinkMacSystemFont,"
    "'Segoe UI',Roboto,'Helvetica Neue',Arial,'Microsoft YaHei',sans-serif;"
    "font-size:14px;color:#333;line-height:1.6"
)
_CONTAINER_STYLE = (
    "max-width:640px;margin:0 auto;background:#fff;border-radius:8px;"
    "box-shadow:0 2px 8px rgba(0,0,0,0.08);overflow:hidden"
)

# Header
_HEADER_STYLE = (
    "background-color:#1a73e8;padding:28px 32px;color:#fff;text-align:center"
)
_HEADER_TITLE_STYLE = "font-size:18px;font-weight:700;margin:0;letter-spacing:0.5px"
_HEADER_SUBTITLE_STYLE = "font-size:13px;margin:6px 0 0 0;opacity:0.85"

# Body
_BODY_STYLE = "padding:24px 32px"

# Section card
_SECTION_STYLE = (
    "margin-bottom:20px;border:1px solid #e8eaed;border-radius:6px;overflow:hidden"
)
_SECTION_HEADER_STYLE = (
    "background-color:#f8f9fa;padding:10px 16px;font-weight:600;font-size:13px;"
    "color:#5f6368;text-transform:uppercase;letter-spacing:0.5px;border-bottom:1px solid #e8eaed"
)

# Table inside section
_TABLE_STYLE = "width:100%;border-collapse:collapse;font-size:14px"
_TH_STYLE = (
    "padding:10px 16px;text-align:left;font-weight:500;color:#5f6368;"
    "background-color:#fafafa;border-bottom:1px solid #e8eaed;width:140px"
)
_TD_STYLE = "padding:10px 16px;border-bottom:1px solid #f0f0f0;color:#333"
_TR_ALT_STYLE = "background-color:#fafbfc"

# Status badge
_STATUS_BADGE_BASE = (
    "display:inline-block;padding:3px 12px;border-radius:12px;font-size:12px;font-weight:600"
)

# Highlight box (for threshold warnings)
_HIGHLIGHT_BOX_STYLE = (
    "background-color:#fef7e0;border-left:4px solid #f9ab00;padding:14px 18px;"
    "border-radius:0 6px 6px 0;margin-bottom:20px;font-size:14px;color:#5f4b00"
)

# Footer
_FOOTER_STYLE = (
    "padding:16px 32px;background-color:#fafafa;border-top:1px solid #e8eaed;"
    "font-size:12px;color:#9aa0a6;text-align:center"
)

# ---------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------

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

_STATUS_COLORS: dict[str, str] = {
    "draft": "#9aa0a6",
    "pending": "#f9ab00",
    "manager_confirm": "#f9ab00",
    "approved": "#0d904f",
    "denied": "#d93025",
    "closed": "#5f6368",
    "finished": "#0d904f",
    "cancelled": "#d93025",
    "activing": "#1a73e8",
    "po_pending": "#f9ab00",
    "po_approved": "#0d904f",
}

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

_TYPE_LABELS: dict[str, str] = {"sc": "SC", "po": "PO", "gr": "GR"}

# Transitions that happen before the entity reaches "pending" status.
# In these stages the formal number (SC No / PO No / GR No) may not
# have been assigned yet — show "待分配" instead of hiding the row.
_EARLY_STAGE_TRANSITIONS = {"create", "submit", "confirm"}


def _status_badge(status: str) -> str:
    """Render a colored status badge."""
    label = _STATUS_LABELS.get(status, status)
    color = _STATUS_COLORS.get(status, "#5f6368")
    return (
        f'<span style="{_STATUS_BADGE_BASE}background-color:{color}1a;color:{color};'
        f'border:1px solid {color}40">{label}</span>'
    )


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


def _field(label: str, value: str, *, alt: bool = False) -> str:
    """Render a single key-value row in the info table."""
    tr_extra = f' style="{_TR_ALT_STYLE}"' if alt else ""
    display = value if value else "-"
    return (
        f'<tr{tr_extra}>'
        f'<td style="{_TH_STYLE}">{label}</td>'
        f'<td style="{_TD_STYLE}">{display}</td>'
        f'</tr>'
    )


def _section(title: str, rows: list[str]) -> str:
    """Wrap rows in a titled section card."""
    if not rows:
        return ""
    return (
        f'<div style="{_SECTION_STYLE}">'
        f'<div style="{_SECTION_HEADER_STYLE}">{title}</div>'
        f'<table style="{_TABLE_STYLE}">'
        + "".join(rows) +
        f'</table>'
        f'</div>'
    )


def _highlight_box(message: str) -> str:
    """Render a highlighted warning/info box."""
    return f'<div style="{_HIGHLIGHT_BOX_STYLE}">{message}</div>'


# ---------------------------------------------------------------
# Entity field builders — exhaustive, grouped by category
# ---------------------------------------------------------------

def _sc_fields(info: dict, show_formal_number: bool, requester_name: str = "") -> list[str]:
    """Build all SC record fields, grouped."""
    alt = False

    def row(label, value):
        nonlocal alt
        r = _field(label, value, alt=alt)
        alt = not alt
        return r

    rows: list[str] = []

    # Basic info
    sc_no = (info.get("sc_no") or "") if show_formal_number else ""
    rows.append(row("SC 编号", sc_no))
    rows.append(row("申请人", requester_name or (info.get("requester_id") or "")))
    rows.append(row("申请类型", info.get("request_type") or ""))
    rows.append(row("成本中心", info.get("cost_center") or ""))
    rows.append(row("SC 金额", _fmt_amount(info.get("sc_amount"))))
    if "consumed_amount" in info:
        rows.append(row("已消费金额", _fmt_amount(info.get("consumed_amount"))))
    if "sc_available_amount" in info:
        rows.append(row("剩余可用金额", _fmt_amount(info.get("sc_available_amount"))))
    rows.append(row("服务期间", _fmt_period(
        info.get("service_period_start"), info.get("service_period_end")
    )))
    rows.append(row("描述", info.get("description") or ""))
    rows.append(row("资产标识", info.get("asset") or ""))
    rows.append(row("资产数量", info.get("asset_nums") or ""))
    rows.append(row("内部系统编号", info.get("internal_system_number") or ""))

    # Dates
    rows.append(row("创建时间", info.get("created_at") or ""))
    rows.append(row("更新时间", info.get("updated_at") or ""))
    rows.append(row("提交时间", info.get("pending_date") or ""))
    rows.append(row("批准时间", info.get("approved_date") or ""))
    rows.append(row("关闭时间", info.get("closed_at") or ""))
    return rows


def _po_fields(info: dict, show_formal_number: bool, requester_name: str = "") -> list[str]:
    """Build all PO fields, grouped."""
    alt = False

    def row(label, value):
        nonlocal alt
        r = _field(label, value, alt=alt)
        alt = not alt
        return r

    rows: list[str] = []

    # Basic
    po_no = (info.get("po_no") or "") if show_formal_number else ""
    rows.append(row("PO 编号", po_no))
    rows.append(row("申请人", requester_name or (info.get("requester_id") or "")))
    rows.append(row("供应商", info.get("vendor_name") or ""))

    # Financial
    rows.append(row("PO 金额", _fmt_amount(info.get("po_amount"))))
    if "consumed_amount" in info:
        rows.append(row("已消费金额", _fmt_amount(info.get("consumed_amount"))))
    if "open_po_amount" in info:
        rows.append(row("剩余可用金额", _fmt_amount(info.get("open_po_amount"))))
    rows.append(row("成本中心", info.get("cost_center") or ""))

    # Contract
    rows.append(row("合同编号", info.get("contract_no") or ""))
    rows.append(row("合同类型", info.get("contract_type") or ""))
    rows.append(row("合同期间", _fmt_period(
        info.get("contract_from"), info.get("contract_to")
    )))
    rows.append(row("合同POS", info.get("contract_pos") or ""))

    # Payment
    rows.append(row("付款频率", info.get("payment_frequency") or ""))

    # Personnel
    rows.append(row("采购员", info.get("purchaser") or ""))

    # Dates
    rows.append(row("激活日期", info.get("activing_date") or ""))
    rows.append(row("创建时间", info.get("created_at") or ""))
    rows.append(row("更新时间", info.get("updated_at") or ""))
    return rows


def _gr_fields(info: dict, show_formal_number: bool, requester_name: str = "") -> list[str]:
    """Build all GR fields, grouped."""
    alt = False

    def row(label, value):
        nonlocal alt
        r = _field(label, value, alt=alt)
        alt = not alt
        return r

    rows: list[str] = []

    # Basic
    gr_no = (info.get("gr_no") or "") if show_formal_number else ""
    rows.append(row("GR 编号", gr_no))
    rows.append(row("申请人", requester_name or (info.get("requester_id") or "")))

    # Financial
    rows.append(row("预估金额 (净价)", _fmt_amount(info.get("estimated_amount"))))
    rows.append(row("确认金额 (含税)", _fmt_amount(info.get("con_value"))))
    rows.append(row("增值税率(%)", info.get("tax_rate") or ""))

    # Description
    rows.append(row("货物/服务描述", info.get("goods_service_description") or ""))
    rows.append(row("备注", info.get("remark") or ""))

    # Confirmation
    rows.append(row("确认名称", info.get("confirmation_name") or ""))

    # Delivery
    rows.append(row("交付期间", _fmt_period(
        info.get("delivery_from"), info.get("delivery_to")
    )))
    rows.append(row("最后交付日", info.get("last_delivery") or ""))

    # Dates
    rows.append(row("创建时间", info.get("created_at") or ""))
    rows.append(row("提交时间", info.get("pending_date") or ""))
    rows.append(row("批准时间", info.get("approved_date") or ""))
    rows.append(row("取消时间", info.get("cancelled_at") or ""))
    rows.append(row("确认时间", info.get("confirmed_at") or ""))
    return rows


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


def _utc_now_cn() -> str:
    """Current time in China Standard Time (UTC+8)."""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M")


def _now_iso() -> str:
    """Current timestamp in ISO format."""
    return datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%dT%H:%M:%S+08:00")


# ---------------------------------------------------------------
# Child PO table (for SC emails)
# ---------------------------------------------------------------

def _child_po_table(child_pos: list[dict]) -> str:
    """Render a table of child POs with budget info for SC emails."""
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">PO 编号</th>'
        f'<th style="{_TH_STYLE}">供应商</th>'
        f'<th style="{_TH_STYLE}">PO 金额</th>'
        f'<th style="{_TH_STYLE}">已消费</th>'
        f'<th style="{_TH_STYLE}">剩余可用</th>'
        f'<th style="{_TH_STYLE}">合同到期</th>'
        f'<th style="{_TH_STYLE}">状态</th>'
        f'</tr>'
    )

    rows: list[str] = []
    for po in child_pos:
        po_no = po.get("po_no") or "-"
        vendor = po.get("vendor_name") or "-"
        po_amount = _fmt_amount(po.get("po_amount"))
        consumed = _fmt_amount(po.get("consumed_amount"))
        open_amt = _fmt_amount(po.get("open_po_amount"))
        contract_to = po.get("contract_to") or "-"
        status = _status_badge(po.get("status") or "")

        tr = (
            f'<tr>'
            f'<td style="{_TD_STYLE}">{po_no}</td>'
            f'<td style="{_TD_STYLE}">{vendor}</td>'
            f'<td style="{_TD_STYLE}">{po_amount}</td>'
            f'<td style="{_TD_STYLE}">{consumed}</td>'
            f'<td style="{_TD_STYLE}">{open_amt}</td>'
            f'<td style="{_TD_STYLE}">{contract_to}</td>'
            f'<td style="{_TD_STYLE}">{status}</td>'
            f'</tr>'
        )
        rows.append(tr)

    table = (
        f'<table style="{_TABLE_STYLE}">'
        f'{header}'
        + "".join(rows) +
        f'</table>'
    )

    return _section(f"关联采购订单 ({len(child_pos)})", [table])


# ---------------------------------------------------------------
# Child GR table (for PO emails)
# ---------------------------------------------------------------

def _child_gr_table(child_grs: list[dict]) -> str:
    """Render a table of child GRs for PO emails."""
    header = (
        f'<tr style="background-color:#f8f9fa">'
        f'<th style="{_TH_STYLE}">GR 编号</th>'
        f'<th style="{_TH_STYLE}">预估金额 (净价)</th>'
        f'<th style="{_TH_STYLE}">确认金额 (含税)</th>'
        f'<th style="{_TH_STYLE}">货物/服务描述</th>'
        f'<th style="{_TH_STYLE}">交付期间</th>'
        f'<th style="{_TH_STYLE}">状态</th>'
        f'</tr>'
    )

    rows: list[str] = []
    for gr in child_grs:
        gr_no = gr.get("gr_no") or "-"
        estimated = _fmt_amount(gr.get("estimated_amount"))
        con_value = _fmt_amount(gr.get("con_value"))
        desc = gr.get("goods_service_description") or "-"
        period = _fmt_period(gr.get("delivery_from"), gr.get("delivery_to"))
        status = _status_badge(gr.get("status") or "")

        tr = (
            f'<tr>'
            f'<td style="{_TD_STYLE}">{gr_no}</td>'
            f'<td style="{_TD_STYLE}">{estimated}</td>'
            f'<td style="{_TD_STYLE}">{con_value}</td>'
            f'<td style="{_TD_STYLE}">{desc}</td>'
            f'<td style="{_TD_STYLE}">{period}</td>'
            f'<td style="{_TD_STYLE}">{status}</td>'
            f'</tr>'
        )
        rows.append(tr)

    table = (
        f'<table style="{_TABLE_STYLE}">'
        f'{header}'
        + "".join(rows) +
        f'</table>'
    )

    return _section(f"关联验收申请 ({len(child_grs)})", [table])


# ---------------------------------------------------------------
# HTML shell
# ---------------------------------------------------------------

def _html_shell(*, title: str, subtitle: str, body: str) -> str:
    """Wrap body content in the unified email HTML template."""
    return (
        f'<!DOCTYPE html>'
        f'<html lang="en">'
        f'<head><meta charset="utf-8"></head>'
        f'<body style="{_PAGE_STYLE}">'
        f'<div style="{_CONTAINER_STYLE}">'
        # Header
        f'<div style="{_HEADER_STYLE}">'
        f'<div style="{_HEADER_TITLE_STYLE}">{title}</div>'
        f'<div style="{_HEADER_SUBTITLE_STYLE}">{subtitle}</div>'
        f'</div>'
        # Body
        f'<div style="{_BODY_STYLE}">'
        f'{body}'
        f'</div>'
        # Footer
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


def build_body(entry: dict, entity_info: dict, user_emails: dict,
               actor_name: str = "", requester_name: str = "") -> str:
    """Build the HTML email body using the modern unified template.

    Shows ALL database fields for the entity, grouped into logical sections.
    Event keys are translated to human-readable Chinese labels.
    """
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry.get("event_key", "")
    event_type = entry.get("event_type", "")
    show_formal_number = event_key not in _EARLY_STAGE_TRANSITIONS

    type_label = _TYPE_LABELS.get(entity_type, entity_type)

    # --- title / subtitle ---
    title = f"{type_label} {entity_id}"
    subtitle = _describe_event(event_type, event_key)

    # --- highlight for threshold events ---
    highlight = ""
    if event_type in ("threshold_date", "threshold_amount"):
        highlight = _highlight_box(
            f"⚠️ <b>{subtitle}</b> — Please handle promptly to avoid business impact."
        )

    # --- status & event section ---
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

    # --- custom schedule description ---
    schedule_rows: list[str] = []
    if event_type == "custom_schedule":
        schedule_desc = _describe_schedule(event_key)
        if schedule_desc:
            schedule_rows.append(_field("提醒计划", schedule_desc, alt=False))

    # --- entity fields ---
    if entity_type == "sc":
        entity_rows = _sc_fields(entity_info, show_formal_number, requester_name)
    elif entity_type == "po":
        entity_rows = _po_fields(entity_info, show_formal_number, requester_name)
    elif entity_type == "gr":
        entity_rows = _gr_fields(entity_info, show_formal_number, requester_name)
    else:
        entity_rows = []

    # --- child POs for SC emails ---
    child_po_section = ""
    if entity_type == "sc" and entity_info.get("child_pos"):
        child_po_section = _child_po_table(entity_info["child_pos"])

    # --- child GRs for PO emails ---
    child_gr_section = ""
    if entity_type == "po" and entity_info.get("child_grs"):
        child_gr_section = _child_gr_table(entity_info["child_grs"])

    # --- assemble body ---
    body_parts = [
        highlight,
        _section("Notification Info", status_rows),
        _section("Reminder Plan", schedule_rows) if schedule_rows else "",
        _section(f"{type_label} Details", entity_rows),
        child_po_section,
        child_gr_section,
    ]

    return _html_shell(
        title=title,
        subtitle=subtitle,
        body="".join(body_parts),
    )


def build_monthly_summary_subject(year: int, month: int) -> str:
    """Subject line for the monthly PO summary email."""
    return f"[POMP] {year}年{month}月 PO月度汇总 — 剩余金额与合同到期提醒"


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
    # Build table rows
    table_rows: list[str] = []
    for i, po in enumerate(po_list):
        po_no = po.get("po_no") or "-"
        sc_no = po.get("sc_no") or "-"
        vendor = po.get("vendor_name") or "-"
        po_amount = f"{po['po_amount']:,.0f}" if po.get("po_amount") else "-"
        open_amount = f"{po['open_po_amount']:,.0f}" if po.get("open_po_amount") else "-"
        contract_to = po.get("contract_to") or "-"
        remaining = po.get("remaining_days")
        remaining_str = f"{remaining} 天" if remaining is not None else "-"
        status = _STATUS_LABELS.get(po.get("status") or "", po.get("status") or "-")

        # Row highlight rules
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
        f'<th style="{_TH_STYLE}">PO 编号</th>'
        f'<th style="{_TH_STYLE}">SC 编号</th>'
        f'<th style="{_TH_STYLE}">供应商</th>'
        f'<th style="{_TH_STYLE}">PO 金额</th>'
        f'<th style="{_TH_STYLE}">剩余金额</th>'
        f'<th style="{_TH_STYLE}">合同到期日</th>'
        f'<th style="{_TH_STYLE}">剩余天数</th>'
        f'<th style="{_TH_STYLE}">状态</th>'
        f'</tr>'
    )

    legend = (
        '<div style="margin-top:16px;font-size:12px;color:#5f6368">'
        '<span style="display:inline-block;width:12px;height:12px;'
        'background-color:#fef7e0;border:1px solid #f9ab00;margin-right:4px;vertical-align:middle"></span> '
        '黄色 = 合同到期不足30天 &nbsp;&nbsp;'
        '<span style="display:inline-block;width:12px;height:12px;'
        'background-color:#fce8e6;border:1px solid #d93025;margin-right:4px;vertical-align:middle"></span> '
        '红色 = 预算剩余不足10%'
        '</div>'
    )

    inner_body = (
        f'<p style="margin:0 0 16px 0">您好 {requester_name}，</p>'
        f'<p style="margin:0 0 20px 0;color:#5f6368">'
        f'以下是您 {year}年{month}月 的采购订单月度汇总，包括各 PO 的剩余金额和合同到期时间：'
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
        title=f"{year}年{month}月 PO 月度汇总",
        subtitle=f"申请人：{requester_name}",
        body=inner_body,
    )
