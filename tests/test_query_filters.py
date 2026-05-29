from datetime import datetime, timezone

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate
from sc_gr_app.services.query_service import search_scs


def test_filter_with_range_suffixes(app_config):
    migrate(app_config)
    timestamp = datetime.now(timezone.utc).isoformat()
    with connect(app_config) as conn:
        conn.execute(
            "INSERT INTO users (user_id, machine_id, user_name, role, status, created_at, updated_at) "
            "VALUES ('U-1', 'M1', 'u1', 'admin', 'active', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, request_type, cost_center, sc_amount, "
            "service_period_start, service_period_end, status, created_by, created_at, updated_at) "
            "VALUES ('SC-A', 'U-1', 'service', 1001, 100, "
            "'2026-01-01', '2026-12-31', 'pending', 'U-1', ?, ?)",
            (timestamp, timestamp),
        )
        conn.execute(
            "INSERT INTO sc_records (sc_id, requester_id, request_type, cost_center, sc_amount, "
            "service_period_start, service_period_end, status, created_by, created_at, updated_at) "
            "VALUES ('SC-B', 'U-1', 'service', 1001, 200, "
            "'2026-06-01', '2026-12-31', 'approved', 'U-1', ?, ?)",
            (timestamp, timestamp),
        )
        conn.commit()

    # Range filter: sc_amount_min
    results = search_scs(app_config, filters={"sc_amount_min": 150}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-B"

    # Range filter: sc_amount_max
    results = search_scs(app_config, filters={"sc_amount_max": 150}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-A"

    # Date range: service_period_start_from
    results = search_scs(app_config, filters={"service_period_start_from": "2026-03-01"}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-B"

    # Date range: service_period_start_to (upper bound)
    results = search_scs(app_config, filters={"service_period_start_to": "2026-03-01"}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-A"

    # Exact match still works
    results = search_scs(app_config, filters={"status": "approved"}, current_user={"role": "admin"})
    assert len(results) == 1
    assert results[0]["sc_id"] == "SC-B"
