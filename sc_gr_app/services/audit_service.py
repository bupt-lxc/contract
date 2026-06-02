import json
from datetime import datetime, timezone
from uuid import uuid4

# Fields excluded from change summaries (pure timestamps / tracking noise)
_SKIP_DIFF_FIELDS = {
    "created_at", "updated_at", "created_by",
    "approved_by", "approved_at", "closed_at",
    "cancelled_by", "cancelled_at",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _diff_changes(before: dict | None, after: dict | None) -> str | None:
    """Produce a human-readable summary of what changed between before and after.

    Returns a semicolon-separated string like ``"sc_amount: 50000 → 80000; status: draft → pending"``,
    or ``None`` if no meaningful diff can be computed.
    """
    if after is None:
        return None
    if before is None:
        # Create — list key fields that were set
        parts = []
        for k, v in after.items():
            if k in _SKIP_DIFF_FIELDS or v is None:
                continue
            val_str = _fmt_val(v)
            parts.append(f"{k}: {val_str}")
        return "; ".join(parts) if parts else None

    # Update — list only fields whose value changed
    parts = []
    for k in after:
        if k in _SKIP_DIFF_FIELDS:
            continue
        old_val = before.get(k)
        new_val = after[k]
        if old_val != new_val:
            parts.append(f"{k}: {_fmt_val(old_val)} → {_fmt_val(new_val)}")
    return "; ".join(parts) if parts else None


def _fmt_val(value) -> str:
    """Format a value for change display — truncate long strings."""
    if value is None:
        return "(空)"
    s = str(value)
    if len(s) > 50:
        s = s[:47] + "..."
    return s


def write_audit_log(
    conn,
    *,
    action_type,
    object_type,
    object_id,
    sc_id,
    operator_id,
    machine_id,
    before,
    after,
    operation_mode="normal",
) -> None:
    changes_summary = _diff_changes(before, after)
    conn.execute(
        """
        insert into audit_logs (
          log_id,
          action_type,
          object_type,
          object_id,
          sc_id,
          operator_id,
          machine_id,
          before_json,
          after_json,
          changes_summary,
          operation_mode,
          created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            action_type,
            object_type,
            object_id,
            sc_id,
            operator_id,
            machine_id,
            json.dumps(before, ensure_ascii=False) if before is not None else None,
            json.dumps(after, ensure_ascii=False) if after is not None else None,
            changes_summary,
            operation_mode,
            utc_now(),
        ),
    )
