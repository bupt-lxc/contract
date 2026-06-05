"""Email subject and body templates (Chinese)."""


def build_subject(entry: dict, entity_info: dict) -> str:
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry["event_key"]

    type_label = {"sc": "SC", "po": "PO", "gr": "GR"}.get(entity_type, entity_type)

    if entry["event_type"] == "status_change":
        transition_labels = {
            "submit": "已提交",
            "create": "已创建",
            "approve": "已批准",
            "deny": "已拒绝",
            "close": "已关闭",
            "finish": "已完成",
            "cancel": "已取消",
        }
        label = transition_labels.get(event_key, event_key)
        return f"[Contract] {type_label} {entity_id} {label}"

    if entry["event_type"] == "threshold_date":
        sc_no = entity_info.get("sc_no") or entity_id
        months = event_key.replace("threshold_date:", "").replace("m", "")
        return f"[Contract] SC {sc_no} 合同即将到期 — 剩余不足{months}个月"

    if entry["event_type"] == "threshold_amount":
        sc_no = entity_info.get("sc_no") or entity_id
        pct = event_key.replace("threshold_amount:", "").replace("%", "")
        return f"[Contract] SC {sc_no} 预算即将耗尽 — 剩余不足{pct}%"

    return f"[Contract] {type_label} {entity_id} — {event_key}"


# Transitions that happen before the entity reaches "pending" status.
# In these stages the formal number (SC No / PO No / GR No) may not
# have been assigned yet — skip it in the email body.
_EARLY_STAGE_TRANSITIONS = {"create", "submit", "confirm"}


def build_body(entry: dict, entity_info: dict, user_emails: dict) -> str:
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]
    event_key = entry.get("event_key", "")
    show_formal_number = event_key not in _EARLY_STAGE_TRANSITIONS

    type_label = {"sc": "SC", "po": "PO", "gr": "GR"}.get(entity_type, entity_type)

    lines = [
        f"<p>This is an automated notification from the Contract Management System.</p>",
        f"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        f"<tr><td><b>Type</b></td><td>{type_label}</td></tr>",
        f"<tr><td><b>ID</b></td><td>{entity_id}</td></tr>",
    ]

    # Entity-specific fields
    if entity_type == "sc":
        sc_no = entity_info.get("sc_no", "") or ""
        sc_amount = entity_info.get("sc_amount", "") or ""
        description = entity_info.get("description", "") or ""
        request_type = entity_info.get("request_type", "") or ""
        cost_center = entity_info.get("cost_center", "") or ""
        service_start = entity_info.get("service_period_start", "") or ""
        service_end = entity_info.get("service_period_end", "") or ""
        if sc_no and show_formal_number:
            lines.append(f"<tr><td><b>SC No</b></td><td>{sc_no}</td></tr>")
        if request_type:
            lines.append(f"<tr><td><b>Request Type</b></td><td>{request_type}</td></tr>")
        if sc_amount:
            lines.append(f"<tr><td><b>SC Amount</b></td><td>{sc_amount}</td></tr>")
        if cost_center:
            lines.append(f"<tr><td><b>Cost Center</b></td><td>{cost_center}</td></tr>")
        if service_start or service_end:
            lines.append(f"<tr><td><b>Service Period</b></td><td>{service_start} ~ {service_end}</td></tr>")
        if description:
            lines.append(f"<tr><td><b>Description</b></td><td>{description}</td></tr>")
    elif entity_type == "po":
        po_no = entity_info.get("po_no", "") or ""
        po_amount = entity_info.get("po_amount", "") or ""
        vendor_name = entity_info.get("vendor_name", "") or ""
        contract_no = entity_info.get("contract_no", "") or ""
        contract_from = entity_info.get("contract_from", "") or ""
        contract_to = entity_info.get("contract_to", "") or ""
        contract_type = entity_info.get("contract_type", "") or ""
        cost_center = entity_info.get("cost_center", "") or ""
        payment_freq = entity_info.get("payment_frequency", "") or ""
        purchaser = entity_info.get("purchaser", "") or ""
        if po_no and show_formal_number:
            lines.append(f"<tr><td><b>PO No</b></td><td>{po_no}</td></tr>")
        if po_amount:
            lines.append(f"<tr><td><b>PO Amount</b></td><td>{po_amount}</td></tr>")
        if vendor_name:
            lines.append(f"<tr><td><b>Vendor</b></td><td>{vendor_name}</td></tr>")
        if contract_no:
            lines.append(f"<tr><td><b>Contract No</b></td><td>{contract_no}</td></tr>")
        if contract_type:
            lines.append(f"<tr><td><b>Contract Type</b></td><td>{contract_type}</td></tr>")
        if contract_from or contract_to:
            lines.append(f"<tr><td><b>Contract Period</b></td><td>{contract_from} ~ {contract_to}</td></tr>")
        if cost_center:
            lines.append(f"<tr><td><b>Cost Center</b></td><td>{cost_center}</td></tr>")
        if payment_freq:
            lines.append(f"<tr><td><b>Payment Frequency</b></td><td>{payment_freq}</td></tr>")
        if purchaser:
            lines.append(f"<tr><td><b>Purchaser</b></td><td>{purchaser}</td></tr>")
    elif entity_type == "gr":
        gr_no = entity_info.get("gr_no", "") or ""
        con_value = entity_info.get("con_value", "") or ""
        estimated_amount = entity_info.get("estimated_amount", "") or ""
        tax_rate = entity_info.get("tax_rate", "") or ""
        goods_desc = entity_info.get("goods_service_description", "") or ""
        confirmation_name = entity_info.get("confirmation_name", "") or ""
        delivery_from = entity_info.get("delivery_from", "") or ""
        delivery_to = entity_info.get("delivery_to", "") or ""
        last_delivery = entity_info.get("last_delivery", "") or ""
        remark = entity_info.get("remark", "") or ""
        if gr_no and show_formal_number:
            lines.append(f"<tr><td><b>GR No</b></td><td>{gr_no}</td></tr>")
        if con_value:
            lines.append(f"<tr><td><b>Gross Cost</b></td><td>{con_value}</td></tr>")
        elif estimated_amount:
            lines.append(f"<tr><td><b>Net Cost</b></td><td>{estimated_amount}</td></tr>")
        if tax_rate:
            lines.append(f"<tr><td><b>VAT(%)</b></td><td>{tax_rate}</td></tr>")
        if goods_desc:
            lines.append(f"<tr><td><b>Goods/Service</b></td><td>{goods_desc}</td></tr>")
        if confirmation_name:
            lines.append(f"<tr><td><b>Confirmation Name</b></td><td>{confirmation_name}</td></tr>")
        if delivery_from or delivery_to:
            lines.append(f"<tr><td><b>Delivery Period</b></td><td>{delivery_from} ~ {delivery_to}</td></tr>")
        if last_delivery:
            lines.append(f"<tr><td><b>Last Delivery</b></td><td>{last_delivery}</td></tr>")
        if remark:
            lines.append(f"<tr><td><b>Remark</b></td><td>{remark}</td></tr>")

    status = entity_info.get("status", "") or ""
    if status:
        lines.append(f"<tr><td><b>Status</b></td><td>{status}</td></tr>")

    lines.append(f"<tr><td><b>Event</b></td><td>{entry['event_key']}</td></tr>")
    lines.append(f"<tr><td><b>Time</b></td><td>{entry['created_at']}</td></tr>")
    lines.append(f"</table>")

    return "\n".join(lines)


def build_monthly_summary_subject(year: int, month: int) -> str:
    """Subject line for the monthly PO summary email."""
    return f"[Contract] {year}年{month}月 PO月度汇总 — 剩余金额与合同到期提醒"


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
    lines = [
        f"<p>Dear {requester_name},</p>",
        f"<p>以下是您 {year}年{month}月 的采购订单月度汇总，包括各PO的剩余金额和合同到期时间：</p>",
        f"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        f"<tr style='background:#f5f5f5'>"
        f"<th>PO No</th><th>SC No</th><th>Vendor</th><th>PO Amount</th>"
        f"<th>Open Amount</th><th>Contract To</th><th>Remaining Days</th><th>Status</th>"
        f"</tr>",
    ]

    for po in po_list:
        po_no = po.get("po_no") or "-"
        sc_no = po.get("sc_no") or "-"
        vendor = po.get("vendor_name") or "-"
        po_amount = f"{po['po_amount']:,.0f}" if po.get("po_amount") else "-"
        open_amount = f"{po['open_po_amount']:,.0f}" if po.get("open_po_amount") else "-"
        contract_to = po.get("contract_to") or "-"
        remaining = po.get("remaining_days")
        remaining_str = f"{remaining} days" if remaining is not None else "-"
        status = po.get("status") or "-"

        # Highlight rows with low remaining budget or close deadlines
        row_style = ""
        if remaining is not None and remaining < 30:
            row_style = " style='background:#fff3cd'"
        elif po.get("open_po_amount") is not None and po.get("po_amount") and po["open_po_amount"] / po["po_amount"] < 0.1:
            row_style = " style='background:#f8d7da'"

        lines.append(
            f"<tr{row_style}>"
            f"<td>{po_no}</td><td>{sc_no}</td><td>{vendor}</td>"
            f"<td>{po_amount}</td><td>{open_amount}</td>"
            f"<td>{contract_to}</td><td>{remaining_str}</td><td>{status}</td>"
            f"</tr>"
        )

    lines.append("</table>")
    lines.append("<p>This is an automated notification from the Contract Management System.</p>")
    lines.append(f"<p><small>Generated: {_utc_now_cn()}</small></p>")

    return "\n".join(lines)


def _utc_now_cn() -> str:
    from datetime import datetime, timezone, timedelta
    return (datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d %H:%M"))
