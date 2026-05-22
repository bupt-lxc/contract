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
        "pos",
        "gr_requests",
        "audit_logs",
        "app_settings",
    }.issubset(tables)


def test_migration_records_versions_once(app_config):
    migrate(app_config)
    migrate(app_config)

    with sqlite3.connect(app_config.db_path) as conn:
        rows = conn.execute(
            "select version, applied_at from schema_migrations order by version"
        ).fetchall()

    assert [row[0] for row in rows] == [1, 2]
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

    assert versions == [1, 2]


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
