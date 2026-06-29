import json
from datetime import datetime

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.record_service import write_operation_record


def test_write_operation_record_inserts_metadata_and_json_payloads(app_config):
    migrate(app_config)
    before = {"status": "pending", "note": "旧值"}
    after = {"status": "approved", "note": "新值"}

    with connect(app_config) as conn:
        write_operation_record(
            conn,
            action_type="approve",
            object_type="gr_request",
            object_id="GR1",
            sc_id="SC1",
            operator_id="U1",
            machine_id="machine1",
            before=before,
            after=after,
            operation_mode="batch",
        )
        conn.commit()

        row = conn.execute("select * from operation_records").fetchone()

    assert row["log_id"]
    assert row["action_type"] == "approve"
    assert row["object_type"] == "gr_request"
    assert row["object_id"] == "GR1"
    assert row["sc_id"] == "SC1"
    assert row["operator_id"] == "U1"
    assert row["machine_id"] == "machine1"
    assert row["operation_mode"] == "batch"
    assert datetime.fromisoformat(row["created_at"]).tzinfo is not None
    assert json.loads(row["before_json"]) == before
    assert json.loads(row["after_json"]) == after
    assert "旧值" in row["before_json"]
    assert "新值" in row["after_json"]


def test_write_operation_record_stores_none_payloads_as_sql_null(app_config):
    migrate(app_config)

    with connect(app_config) as conn:
        write_operation_record(
            conn,
            action_type="view",
            object_type="sc_record",
            object_id="SC1",
            sc_id="SC1",
            operator_id="U1",
            machine_id="machine1",
            before=None,
            after=None,
        )
        conn.commit()

        row = conn.execute(
            "select before_json, after_json from operation_records"
        ).fetchone()

    assert row["before_json"] is None
    assert row["after_json"] is None
