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
        if sc_no and show_formal_number:
            lines.append(f"<tr><td><b>SC No</b></td><td>{sc_no}</td></tr>")
        if sc_amount:
            lines.append(f"<tr><td><b>Amount</b></td><td>{sc_amount}</td></tr>")
        if description:
            lines.append(f"<tr><td><b>Description</b></td><td>{description}</td></tr>")
    elif entity_type == "po":
        po_no = entity_info.get("po_no", "") or ""
        po_amount = entity_info.get("po_amount", "") or ""
        if po_no and show_formal_number:
            lines.append(f"<tr><td><b>PO No</b></td><td>{po_no}</td></tr>")
        if po_amount:
            lines.append(f"<tr><td><b>Amount</b></td><td>{po_amount}</td></tr>")
    elif entity_type == "gr":
        gr_no = entity_info.get("gr_no", "") or ""
        con_value = entity_info.get("con_value", "") or ""
        estimated_amount = entity_info.get("estimated_amount", "") or ""
        if gr_no and show_formal_number:
            lines.append(f"<tr><td><b>GR No</b></td><td>{gr_no}</td></tr>")
        if con_value:
            lines.append(f"<tr><td><b>Contract Value</b></td><td>{con_value}</td></tr>")
        elif estimated_amount:
            lines.append(f"<tr><td><b>Estimated Amount</b></td><td>{estimated_amount}</td></tr>")

    status = entity_info.get("status", "") or ""
    if status:
        lines.append(f"<tr><td><b>Status</b></td><td>{status}</td></tr>")

    lines.append(f"<tr><td><b>Event</b></td><td>{entry['event_key']}</td></tr>")
    lines.append(f"<tr><td><b>Time</b></td><td>{entry['created_at']}</td></tr>")
    lines.append(f"</table>")

    return "\n".join(lines)
