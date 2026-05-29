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


def build_body(entry: dict, entity_info: dict, user_emails: dict) -> str:
    entity_type = entry["entity_type"]
    entity_id = entry["entity_id"]

    type_label = {"sc": "SC", "po": "PO", "gr": "GR"}.get(entity_type, entity_type)
    sc_no = entity_info.get("sc_no", "") or ""
    sc_amount = entity_info.get("sc_amount", "") or ""
    description = entity_info.get("description", "") or ""
    status = entity_info.get("status", "") or ""

    lines = [
        f"<p>This is an automated notification from the Contract Management System.</p>",
        f"<table border='1' cellpadding='4' cellspacing='0' style='border-collapse:collapse'>",
        f"<tr><td><b>Type</b></td><td>{type_label}</td></tr>",
        f"<tr><td><b>ID</b></td><td>{entity_id}</td></tr>",
    ]
    if sc_no:
        lines.append(f"<tr><td><b>SC No</b></td><td>{sc_no}</td></tr>")
    if sc_amount:
        lines.append(f"<tr><td><b>Amount</b></td><td>{sc_amount}</td></tr>")
    if status:
        lines.append(f"<tr><td><b>Status</b></td><td>{status}</td></tr>")
    if description:
        lines.append(f"<tr><td><b>Description</b></td><td>{description}</td></tr>")

    lines.append(f"<tr><td><b>Event</b></td><td>{entry['event_key']}</td></tr>")
    lines.append(f"<tr><td><b>Time</b></td><td>{entry['created_at']}</td></tr>")
    lines.append(f"</table>")

    return "\n".join(lines)
