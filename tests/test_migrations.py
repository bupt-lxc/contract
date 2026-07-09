import sqlite3

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import SCHEMA_VERSION, migrate


EXPECTED_MIGRATION_VERSIONS = [
    *range(1, 6),
    *range(7, SCHEMA_VERSION + 1),
]


def test_migration_creates_core_tables(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        tables = {
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        }

    assert {
        "schema_migrations",
        "users",
        "sc_records",
        "vendors",
        "sc_vendors",
        "pos",
        "gr_requests",
        "operation_records",
        "app_settings",
    }.issubset(tables)


def test_sc_vendors_has_vendor_snapshot_column(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(sc_vendors)")
        }
    assert "vendor_snapshot" in columns


def test_migration_records_versions_once(app_config):
    migrate(app_config)
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        rows = conn.execute(
            "select version, applied_at from schema_migrations order by version"
        ).fetchall()

    assert [row[0] for row in rows] == EXPECTED_MIGRATION_VERSIONS
    assert rows[0][1]
    assert rows[1][1]


def test_migration_records_version_two(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        versions = [
            row[0]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            )
        ]

    assert versions == EXPECTED_MIGRATION_VERSIONS

def test_sc_records_supports_draft_and_nullable_business_fields(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, description,
              created_by, created_at, updated_at, approved_by, approved_at, finished_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SC_DRAFT",
                None,
                "U1",
                None,
                None,
                None,
                None,
                None,
                "draft",
                None,
                "U1",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
                None,
                None,
                None,
            ),
        )
        row = conn.execute(
            "select status, request_type, sc_amount from sc_records where sc_id = 'SC_DRAFT'"
        ).fetchone()

    assert row == ("draft", None, None)


def test_sc_records_requires_business_fields_after_draft(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )

        try:
            conn.execute(
                """
                insert into sc_records (
                  sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
                  service_period_start, service_period_end, status, description,
                  created_by, created_at, updated_at, approved_by, approved_at, finished_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SC_PENDING",
                    None,
                    "U1",
                    None,
                    1001,
                    1000,
                    "2026-01-01",
                    "2026-12-31",
                    "pending",
                    None,
                    "U1",
                    "2026-05-22T00:00:00+00:00",
                    "2026-05-22T00:00:00+00:00",
                    None,
                    None,
                    None,
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("pending SC with null request_type should fail")


def test_migration_repairs_recorded_v2_without_business_field_check(app_config):
    with connect(app_config) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE users (
              user_id TEXT PRIMARY KEY,
              machine_id TEXT NOT NULL UNIQUE,
              user_name TEXT NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('admin', 'requester')),
              email TEXT,
              status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE sc_records (
              sc_id TEXT PRIMARY KEY,
              sc_no TEXT,
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
              cost_center INTEGER,
              sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
              service_period_start TEXT,
              service_period_end TEXT,
              status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'denied', 'closed')),
              description TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              closed_at TEXT
            );
            """
        )
        conn.execute(
            "insert into schema_migrations(version, applied_at) values (?, ?)",
            (1, "2026-05-22T00:00:00+00:00"),
        )
        conn.execute(
            "insert into schema_migrations(version, applied_at) values (?, ?)",
            (2, "2026-05-22T00:00:00+00:00"),
        )
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.commit()

    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        versions = [
            row[0]
            for row in conn.execute(
                "select version from schema_migrations order by version"
            )
        ]
        try:
            conn.execute(
                """
                insert into sc_records (
                  sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
                  service_period_start, service_period_end, status, description,
                  created_by, created_at, updated_at, approved_by, approved_at, finished_at
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "SC_PENDING",
                    None,
                    "U1",
                    None,
                    1001,
                    1000,
                    "2026-01-01",
                    "2026-12-31",
                    "pending",
                    None,
                    "U1",
                    "2026-05-22T00:00:00+00:00",
                    "2026-05-22T00:00:00+00:00",
                    None,
                    None,
                    None,
                ),
            )
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("repaired v2 should reject missing business fields")

    assert versions == EXPECTED_MIGRATION_VERSIONS

def test_migration_reports_invalid_recorded_v2_sc_rows_before_rebuild(app_config):
    with connect(app_config) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE users (
              user_id TEXT PRIMARY KEY,
              machine_id TEXT NOT NULL UNIQUE,
              user_name TEXT NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('admin', 'requester')),
              email TEXT,
              status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE sc_records (
              sc_id TEXT PRIMARY KEY,
              sc_no TEXT,
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              request_type TEXT CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
              cost_center INTEGER,
              sc_amount REAL CHECK (sc_amount IS NULL OR sc_amount > 0),
              service_period_start TEXT,
              service_period_end TEXT,
              status TEXT NOT NULL CHECK (status IN ('draft', 'pending', 'approved', 'denied', 'closed')),
              description TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              closed_at TEXT
            );
            """
        )
        conn.execute(
            "insert into schema_migrations(version, applied_at) values (?, ?)",
            (1, "2026-05-22T00:00:00+00:00"),
        )
        conn.execute(
            "insert into schema_migrations(version, applied_at) values (?, ?)",
            (2, "2026-05-22T00:00:00+00:00"),
        )
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, description,
              created_by, created_at, updated_at, approved_by, approved_at, closed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SC_BAD1",
                None,
                "U1",
                None,
                1001,
                1000,
                "2026-01-01",
                "2026-12-31",
                "pending",
                None,
                "U1",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
                None,
                None,
                None,
            ),
        )
        conn.commit()

    try:
        migrate(app_config)
    except RuntimeError as exc:
        message = str(exc)
    else:
        raise AssertionError("invalid recorded-v2 SC row should abort migration")

    assert "Invalid SC records cannot be migrated" in message
    assert "SC_BAD1" in message


def test_migration_v2_preserves_dependent_foreign_keys_and_indexes(app_config):
    with connect(app_config) as conn:
        conn.executescript(
            """
            CREATE TABLE schema_migrations (
              version INTEGER PRIMARY KEY,
              applied_at TEXT NOT NULL
            );

            CREATE TABLE users (
              user_id TEXT PRIMARY KEY,
              machine_id TEXT NOT NULL UNIQUE,
              user_name TEXT NOT NULL,
              role TEXT NOT NULL CHECK (role IN ('admin', 'requester')),
              email TEXT,
              status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE sc_records (
              sc_id TEXT PRIMARY KEY,
              sc_no TEXT,
              requester_id TEXT NOT NULL REFERENCES users(user_id),
              request_type TEXT NOT NULL CHECK (request_type IN ('material', 'service', 'fixed_asset', 'FC')),
              cost_center INTEGER NOT NULL,
              sc_amount REAL NOT NULL CHECK (sc_amount > 0),
              service_period_start TEXT NOT NULL,
              service_period_end TEXT NOT NULL,
              status TEXT NOT NULL CHECK (status IN ('pending', 'approved', 'denied', 'closed')),
              description TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              approved_by TEXT REFERENCES users(user_id),
              approved_at TEXT,
              closed_at TEXT
            );

            CREATE TABLE vendors (
              vendor_id TEXT PRIMARY KEY,
              vendor_name TEXT NOT NULL,
              ksrm_vendor_code TEXT,
              contact_person TEXT,
              phone TEXT,
              service_scope TEXT NOT NULL,
              email TEXT,
              description TEXT,
              inquiry_history TEXT,
              created_by TEXT NOT NULL REFERENCES users(user_id),
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );

            CREATE TABLE pos (
              po_id TEXT PRIMARY KEY,
              sc_id TEXT NOT NULL REFERENCES sc_records(sc_id),
              vendor_id TEXT NOT NULL REFERENCES vendors(vendor_id),
              po_no TEXT,
              po_amount REAL NOT NULL CHECK (po_amount > 0),
              status TEXT NOT NULL CHECK (status IN ('po_pending', 'po_pending', 'finished')),
              contract_from TEXT,
              contract_to TEXT,
              contract_no TEXT,
              payment_frequency TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            "insert into schema_migrations(version, applied_at) values (?, ?)",
            (1, "2026-05-22T00:00:00+00:00"),
        )
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "U1",
                "M1",
                "Requester",
                "requester",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into users (
              user_id, machine_id, user_name, role, email, status, created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "A1",
                "M2",
                "Admin",
                "admin",
                None,
                "active",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into vendors (
              vendor_id, vendor_name, ksrm_vendor_code, contact_person, phone,
              service_scope, email, description, inquiry_history, created_by,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "V1",
                "Vendor",
                None,
                None,
                None,
                "Others",
                None,
                None,
                None,
                "A1",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.execute(
            """
            insert into sc_records (
              sc_id, sc_no, requester_id, request_type, cost_center, sc_amount,
              service_period_start, service_period_end, status, description,
              created_by, created_at, updated_at, approved_by, approved_at, closed_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "SC1",
                "SC-001",
                "U1",
                "service",
                1001,
                1000,
                "2026-01-01",
                "2026-12-31",
                "approved",
                None,
                "U1",
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
                "A1",
                "2026-05-22T00:00:00+00:00",
                None,
            ),
        )
        conn.execute(
            """
            insert into pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status,
              contract_from, contract_to, contract_no, payment_frequency,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PO1",
                "SC1",
                "V1",
                "PO-001",
                500,
                "po_pending",
                None,
                None,
                None,
                None,
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )
        conn.commit()

    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        fk_errors = conn.execute("PRAGMA foreign_key_check").fetchall()
        po_fk_targets = [
            row[2]
            for row in conn.execute("PRAGMA foreign_key_list(pos)")
            if row[3] == "sc_id"
        ]
        sc_indexes = {
            row[1]
            for row in conn.execute("PRAGMA index_list(sc_records)")
        }
        po_row = conn.execute(
            "select sc_id from pos where po_id = 'PO1'"
        ).fetchone()
        conn.execute(
            """
            insert into pos (
              po_id, sc_id, vendor_id, po_no, po_amount, status,
              contract_from, contract_to, contract_no, payment_frequency,
              created_at, updated_at
            ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "PO2",
                "SC1",
                "V1",
                "PO-002",
                250,
                "active",
                None,
                None,
                None,
                None,
                "2026-05-22T00:00:00+00:00",
                "2026-05-22T00:00:00+00:00",
            ),
        )

    assert fk_errors == []
    assert po_fk_targets == ["sc_records"]
    assert po_row == ("SC1",)
    assert {"idx_sc_records_requester", "idx_sc_records_status"}.issubset(sc_indexes)


def test_connection_enables_required_pragmas(app_config):
    with connect(app_config) as conn:
        foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]

    assert foreign_keys == 1
    assert journal_mode == "delete"


def test_gr_requests_schema_uses_po_link_and_con_value(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        columns = {
            row[1]
            for row in conn.execute("PRAGMA table_info(gr_requests)")
        }

    assert {"po_id", "con_value"}.issubset(columns)
    assert not {
        "sc_id",
        "reason",
        "finance_reference_no",
        "actual_amount",
    }.intersection(columns)


def test_open_po_amount_is_not_stored(app_config):
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        table_names = [
            row[0]
            for row in conn.execute(
                "select name from sqlite_master where type='table'"
            )
        ]
        columns = {
            column[1]
            for table_name in table_names
            for column in conn.execute(f"PRAGMA table_info({table_name})")
        }

    assert "open_po_amount" not in columns


def test_migrate_creates_backup_when_pending_migrations_exist(app_config):
    """When migrations are pending, a timestamped .sqlite3.bak file is created."""
    from sc_gr_app.db.migrations import _migrate_v1

    # Run v1 to create all core tables, then remove all schema_migrations
    # records so that subsequent migrate() sees all versions as pending
    with sqlite3.connect(app_config.db_path) as conn:
        _migrate_v1(conn)
        conn.execute("DELETE FROM schema_migrations")
        conn.commit()

    from pathlib import Path
    db_path = Path(app_config.db_path)
    original_size = db_path.stat().st_size

    existing_baks = list(db_path.parent.glob(f"{db_path.stem}_*.sqlite3.bak"))

    migrate(app_config)

    new_baks = list(db_path.parent.glob(f"{db_path.stem}_*.sqlite3.bak"))
    assert len(new_baks) == len(existing_baks) + 1
    assert new_baks[-1].stat().st_size == original_size


def test_migrate_skips_backup_when_no_pending_migrations(app_config):
    """When DB is already at latest version, no backup is created."""
    # First, create the DB file so it exists before migrate()
    from pathlib import Path
    db_path = Path(app_config.db_path)
    db_path.touch()

    # First migrate: DB is empty but exists, so a backup IS created
    migrate(app_config)

    existing_baks = set(db_path.parent.glob(f"{db_path.stem}_*.sqlite3.bak"))
    assert len(existing_baks) == 1  # backup from first migrate

    # Second migrate: all versions applied, no new backup
    migrate(app_config)

    after_baks = set(db_path.parent.glob(f"{db_path.stem}_*.sqlite3.bak"))
    assert after_baks == existing_baks


def test_migration_v35(fresh_db, app_config):
    """v35: remaps request_type, renames service_scope values, adds service_scope column."""
    conn = fresh_db
    # Seed old-style data
    conn.execute(
        "INSERT INTO users (user_id, machine_id, user_name, role, created_at, updated_at) "
        "VALUES ('U1', 'M1', 'Test', 'admin', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
        "VALUES ('V1', 'Test Vendor', 'engineering Service', 'U1', '2026-01-01', '2026-01-01')"
    )
    conn.execute(
        "INSERT INTO vendors (vendor_id, vendor_name, service_scope, created_by, created_at, updated_at) "
        "VALUES ('V2', 'Test Vendor 2', 'Maintenance', 'U1', '2026-01-01', '2026-01-01')"
    )

    from sc_gr_app.db.migrations import _migrate_v35
    # Manually set version
    conn.execute("DELETE FROM schema_migrations WHERE version = 35")
    _migrate_v35(conn)

    # Verify vendor service_scope renamed
    row = conn.execute("SELECT service_scope FROM vendors WHERE vendor_id = 'V1'").fetchone()
    assert row["service_scope"] == "Engineering Service"
    row = conn.execute("SELECT service_scope FROM vendors WHERE vendor_id = 'V2'").fetchone()
    assert row["service_scope"] == "Maintenance&Calibration"

    # Verify service_scope column exists on sc_records
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(sc_records)")}
    assert "service_scope" in cols


def test_migration_backfills_missing_old_versions_without_rebuilding_newer_gr_schema(fresh_db, app_config):
    """Missing old migration records should not drop newer v38 cancellation data."""
    conn = fresh_db
    conn.execute("DELETE FROM schema_migrations WHERE version IN (34, 35)")
    conn.execute(
        """
        INSERT INTO gr_requests (
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          status, created_by, created_at, is_cancellation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "GR-CANCEL",
            "GR-CANCEL",
            "PO-SEED",
            "U000001",
            -100,
            -100,
            "draft",
            "U000001",
            "2026-01-01",
            "Y",
        ),
    )
    conn.commit()
    conn.close()

    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as verify_conn:
        versions = [
            row[0]
            for row in verify_conn.execute(
                "SELECT version FROM schema_migrations ORDER BY version"
            )
        ]
        row = verify_conn.execute(
            "SELECT is_cancellation FROM gr_requests WHERE gr_id = ?",
            ("GR-CANCEL",),
        ).fetchone()

    assert versions == EXPECTED_MIGRATION_VERSIONS
    assert row[0] == "Y"


def test_migration_v38_preserves_existing_cancellation_values(fresh_db, app_config):
    conn = fresh_db
    conn.execute("DELETE FROM schema_migrations WHERE version = 38")
    conn.execute(
        """
        INSERT INTO gr_requests (
          gr_id, gr_no, po_id, requester_id, estimated_amount, con_value,
          status, created_by, created_at, is_cancellation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "GR-CANCEL-V38",
            "GR-CANCEL-V38",
            "PO-SEED",
            "U000001",
            -100,
            -100,
            "draft",
            "U000001",
            "2026-01-01",
            "Y",
        ),
    )
    conn.commit()
    conn.close()

    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as verify_conn:
        row = verify_conn.execute(
            "SELECT is_cancellation FROM gr_requests WHERE gr_id = ?",
            ("GR-CANCEL-V38",),
        ).fetchone()

    assert row[0] == "Y"
