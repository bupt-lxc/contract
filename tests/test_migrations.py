import sqlite3

from sc_gr_app.db.connection import connect
from sc_gr_app.db.migrations import migrate


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
        "audit_logs",
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

    assert [row[0] for row in rows] == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]
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

    assert versions == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


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
              created_by, created_at, updated_at, approved_by, approved_at, closed_at
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
                  created_by, created_at, updated_at, approved_by, approved_at, closed_at
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
                  created_by, created_at, updated_at, approved_by, approved_at, closed_at
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

    assert versions == [1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]


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
                "activing",
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
