from pathlib import Path

import pytest

from sc_gr_app.config import AppConfig


@pytest.fixture()
def app_config(tmp_path: Path) -> AppConfig:
    return AppConfig(
        db_path=tmp_path / "test.sqlite3",
        lock_dir=tmp_path / "locks",
        busy_timeout_ms=1000,
    )


@pytest.fixture()
def seeded_config(app_config: AppConfig) -> AppConfig:
    """Migrate + seed users, return config ready for tests."""
    from sc_gr_app.db.migrations import migrate
    from sc_gr_app.services.user_service import seed_users

    migrate(app_config)
    seed_users(app_config)
    return app_config


@pytest.fixture()
def sample_data(seeded_config: AppConfig) -> AppConfig:
    """Create sample GRs across years and statuses for annual report testing."""
    import sqlite3
    conn = sqlite3.connect(seeded_config.db_path)
    conn.executescript("""
        INSERT OR IGNORE INTO users (user_id, machine_id, user_name, role, email, status, created_at, updated_at)
        VALUES ('u1', 'M000001', 'Test User 1', 'admin', 'u1@test.com', 'active', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO sc_records (sc_id, sc_no, requester_id, request_type, cost_center, sc_amount, service_period_start, service_period_end, status, description, created_by, created_at, updated_at)
        VALUES ('sc-001', 'SC-2026-001', 'u1', 'new', 60473000, 100000, '2026-01-01', '2026-12-31', 'approved', 'Test SC', 'u1', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at)
        VALUES ('v-001', 'Test Vendor', 'General Service', 'u1', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        INSERT OR IGNORE INTO pos (po_id, sc_id, vendor_id, po_no, po_amount, status, created_at, updated_at)
        VALUES ('po-001', 'sc-001', 'v-001', 'PO-2026-001', 80000, 'active', '2026-01-01T00:00:00', '2026-01-01T00:00:00');

        -- Finished GR in 2026
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at, finished_at, approved_date)
        VALUES ('gr-001', 'GR-001', 'po-001', 'u1', 50000, 50000, 'finished', 'u1', '2026-03-01T00:00:00', '2026-06-15T00:00:00', '2026-05-01T00:00:00');

        -- Approved GR in 2026
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, con_value, status, created_by, created_at, approved_date)
        VALUES ('gr-002', 'GR-002', 'po-001', 'u1', 30000, 30000, 'approved', 'u1', '2026-04-01T00:00:00', '2026-07-01T00:00:00');

        -- Pending GR in 2026 (should NOT appear in results)
        INSERT OR IGNORE INTO gr_requests (gr_id, gr_no, po_id, requester_id, estimated_amount, status, created_by, created_at)
        VALUES ('gr-003', 'GR-003', 'po-001', 'u1', 10000, 'pending', 'u1', '2026-05-01T00:00:00');
    """)
    conn.commit()
    conn.close()
    return seeded_config


@pytest.fixture()
def fresh_db(seeded_config: AppConfig):
    """Fresh database connection after full migration (for migration re-run tests)."""
    import sqlite3
    conn = sqlite3.connect(seeded_config.db_path)
    conn.row_factory = sqlite3.Row
    yield conn
    conn.close()
