import json
from datetime import datetime, timezone
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
          operation_mode,
          created_at
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            operation_mode,
            utc_now(),
        ),
    )
